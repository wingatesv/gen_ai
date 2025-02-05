import sys
import os
import json
import datetime
import shutil
import yaml
import subprocess
import logging
from concurrent.futures import ThreadPoolExecutor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QFileDialog, QMessageBox, QMenu, QWidget, QHBoxLayout, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QThread
from PyQt5.uic import loadUi
from llm_query import initialize_rag, hugging_face_query

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler('application.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(file_handler)

class RAGWorker(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, api_token, embedding_model, llm_model, chunk_size, chunk_overlap):
        super().__init__()
        self.api_token = api_token
        self.embedding_model = embedding_model
        self.llm_model = llm_model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def run(self):
        try:
            initialize_rag(
                api_token=self.api_token,
                embedding_model=self.embedding_model,
                llm_model=self.llm_model,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap
            )
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

class MainWindow(QMainWindow):
    response_ready = pyqtSignal(str)

    def __init__(self):
        logging.debug("Initializing MainWindow")
        super().__init__()
        loadUi("resources/interface.ui", self)

        # Load configuration from YAML
        self.config = self.load_config("config.yaml")

        # Configuration
        self.api_token = self.config.get("API_TOKEN", "")
        self.embedding_model = self.config.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
        self.llm_model = self.config.get("LLM_MODEL", "google/gemma-2-2b-it")
        self.chunk_size = self.config.get("CHUNK_SIZE", 512)
        self.chunk_overlap = self.config.get("CHUNK_OVERLAP", 10)

        # Initialize RAG
        logging.debug("Initializing RAG")
        initialize_rag(
            api_token=self.api_token,
            embedding_model=self.embedding_model,
            llm_model=self.llm_model,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap
        )

        # Signals and UI setup
        self.response_ready.connect(self.handle_response)
        self.uploadButton.clicked.connect(self.upload_files)
        self.sendButton.clicked.connect(self.send_query)
        self.documentList.setContextMenuPolicy(Qt.CustomContextMenu)
        self.documentList.customContextMenuRequested.connect(self.show_context_menu)
        self.splitter.setSizes([200, self.width() - 200])

        # Enable drag and drop for leftPanel
        self.leftPanel.setAcceptDrops(True)
        self.leftPanel.dragEnterEvent = self.dragEnterEvent
        self.leftPanel.dropEvent = self.dropEvent

        # Internal state
        self.internal_folder = self._setup_internal_folder("documents")
        self.uploaded_files = []
        self.update_document_list()

        # Chat management panel
        self.current_session_file = None  # Track the currently loaded/saved chat session file
        self.chatHistoryList.itemClicked.connect(self.load_chat_session)
        self.load_existing_chat_sessions()

        # Connect the new chat button (with '+' symbol) to create a new session.
        self.newChatButton.clicked.connect(self.new_chat_session)

    @staticmethod
    def load_config(config_path):
        """Load configuration from a YAML file."""
        logging.debug(f"Loading configuration from {config_path}")
        if not os.path.exists(config_path):
            logging.critical(f"Missing configuration file: {config_path}")
            QMessageBox.critical(None, "Configuration Error", f"Missing configuration file: {config_path}")
            sys.exit(1)
        
        try:
            with open(config_path, "r") as file:
                return yaml.safe_load(file)
        except Exception as e:
            logging.critical(f"Failed to read config file: {e}")
            QMessageBox.critical(None, "Configuration Error", f"Failed to read config file:\n{str(e)}")
            sys.exit(1)

    @staticmethod
    def _setup_internal_folder(folder_name):
        """Create and return the internal folder path."""
        logging.debug(f"Setting up internal folder: {folder_name}")
        folder_path = os.path.join(os.getcwd(), folder_name)
        os.makedirs(folder_path, exist_ok=True)
        return folder_path

    def update_document_list(self):
        """Populate the document list with files from the internal folder."""
        logging.debug("Updating document list")
        self.documentList.clear()
        self.uploaded_files = [
            file for file in os.listdir(self.internal_folder) if file.endswith((".pdf", ".docx", ".txt", ".csv", ".json"))
        ]
        self.documentList.addItems(self.uploaded_files)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        self.upload_files_drag_drop(files)

    def upload_files_drag_drop(self, file_paths):
        new_files = []
        for file_path in file_paths:
            file_name = os.path.basename(file_path)
            shutil.copy(file_path, os.path.join(self.internal_folder, file_name))
            self.uploaded_files.append(file_name)
            self.documentList.addItem(file_name)
            new_files.append(file_name)  # Add to list of new files

        if new_files:
            logging.info(f"Uploaded new files: {new_files}")
            QMessageBox.information(self, "Upload Successful", "Document(s) uploaded successfully!")
            self.update_document_list()
            self.run_initialize_rag(new_files)

    def upload_files(self):
        """Handle file upload and update the RAG database."""
        logging.debug("Uploading documents")
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Documents", "", "Documents (*.pdf *.docx *.txt *.csv *.json)"
        )
        if not files:
            logging.debug("No files selected for upload")
            return

        new_files = []  # Track new files that are added

        for file_path in files:
            file_name = os.path.basename(file_path)
            if file_name in self.uploaded_files:
                logging.warning(f"Duplicate file: {file_name}")
                QMessageBox.warning(self, "Duplicate File", f"'{file_name}' is already uploaded.")
                continue  # Skip duplicate files

            shutil.copy(file_path, os.path.join(self.internal_folder, file_name))
            self.uploaded_files.append(file_name)
            self.documentList.addItem(file_name)
            new_files.append(file_name)  # Add to list of new files

        if new_files:
            logging.info(f"Uploaded new files: {new_files}")
            QMessageBox.information(self, "Upload Successful", "Document(s) uploaded successfully!")
            self.update_document_list()
            self.run_initialize_rag(new_files)

    def run_initialize_rag(self, new_files):
        logging.debug(f"Updating RAG with {len(new_files)} new file(s)")
        # self.worker = RAGWorker(
        #     api_token=self.api_token,
        #     embedding_model=self.embedding_model,
        #     llm_model=self.llm_model,
        #     chunk_size=self.chunk_size,
        #     chunk_overlap=self.chunk_overlap
        # )
        # self.worker.finished.connect(self.on_rag_finished)
        # self.worker.error.connect(self.on_rag_error)
        # self.worker.start()
        logging.debug("RAG update started")
        QMessageBox.information(self, "RAG Update", "Updating RAG database in the background.")

    def on_rag_finished(self):
        logging.info("RAG update completed")
        QMessageBox.information(self, "RAG Update", "RAG database update completed successfully!")

    def on_rag_error(self, error_message):
        logging.error(f"RAG update failed: {error_message}")
        QMessageBox.critical(self, "RAG Update Error", f"RAG database update failed.\n{error_message}")

    def show_context_menu(self, position):
        """Show context menu for the document list."""
        logging.debug("Showing context menu")
        item = self.documentList.itemAt(position)
        if item:
            menu = QMenu()
            open_action = menu.addAction("Open File")
            delete_action = menu.addAction("Delete File")
            selected_action = menu.exec_(self.documentList.mapToGlobal(position))
            if selected_action == delete_action:
                self.delete_file(item)
            elif selected_action == open_action:
                self.open_file(item)

    def open_file(self, item):
        """Open the selected file."""
        file_name = item.text()
        file_path = os.path.join(self.internal_folder, file_name)
        logging.debug(f"Opening file: {file_name}")
        try:
            os.startfile(file_path)  # For Windows
        except AttributeError:
            subprocess.call(('open', file_path))  # For macOS
        except Exception as e:
            logging.error(f"Failed to open '{file_name}': {e}")
            QMessageBox.critical(self, "Error", f"Failed to open '{file_name}'.\n{str(e)}")

    def delete_file(self, item):
        """Delete the selected file."""
        file_name = item.text()
        file_path = os.path.join(self.internal_folder, file_name)
        logging.debug(f"Deleting file: {file_name}")

        if QMessageBox.question(
            self, "Delete File", f"Are you sure you want to delete '{file_name}'?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            try:
                os.remove(file_path)
                self.documentList.takeItem(self.documentList.row(item))
                self.uploaded_files.remove(file_name)
                logging.info(f"Deleted file: {file_name}")
                QMessageBox.information(self, "Delete Successful", f"'{file_name}' has been deleted.")
            except Exception as e:
                logging.error(f"Failed to delete '{file_name}': {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete '{file_name}'.\n{str(e)}")

    def show_dot_animation(self):
        """Show a loading animation while waiting for the response."""
        logging.debug("Showing dot animation")
        self.dot_label = QLabel("Loading")
        self.dot_label.setStyleSheet("background-color: #191970; border-radius: 10px; padding: 10px;")
        self.add_message(self.dot_label, sender="model")

        self.dot_timer = QTimer(self)
        self.dot_count = 0
        self.dot_timer.timeout.connect(self.update_dot_animation)
        self.dot_timer.start(500)

    def update_dot_animation(self):
        """Update the dot animation."""
        self.dot_count = (self.dot_count + 1) % 4
        self.dot_label.setText("Loading" + "." * self.dot_count)

    def remove_dot_animation(self):
        """Remove the dot animation."""
        logging.debug("Removing dot animation")
        if hasattr(self, "dot_timer"):
            self.dot_timer.stop()
        if hasattr(self, "dot_label"):
            self.chatLayout.removeWidget(self.dot_label)
            self.dot_label.deleteLater()

    def send_query(self):
        """Send a query to the LLM and handle the response."""
        user_input = self.promptInput.text().strip()
        if not user_input:
            logging.debug("No user input to send")
            return

        logging.debug(f"Sending query: {user_input}")
        self.add_message(user_input, sender="user")
        self.promptInput.clear()
        self.show_dot_animation()

        def query_llm():
            # return str(hugging_face_query(user_input))
            return user_input

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(query_llm)
        future.add_done_callback(lambda f: self.response_ready.emit(f.result()))

    def handle_response(self, response):
        """Handle the response from the LLM."""
        logging.debug(f"Handling response: {response}")
        self.remove_dot_animation()
        self.add_message(response, sender="model")

    def add_message(self, text_or_widget, sender):
        """Add a message bubble or widget to the chat layout."""
        logging.debug(f"Adding message from {sender}")
        if isinstance(text_or_widget, str):
            # Create a QLabel for text and store the sender info.
            label = QLabel(text_or_widget)
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            # Set the sender property
            label.setProperty("sender", sender)

            # Dynamically adjust the label's width based on text
            font_metrics = label.fontMetrics()
            text_width = font_metrics.boundingRect(text_or_widget).width()
            max_width = 400  # Maximum width for the label
            width = min(text_width + 20, max_width)
            label.setFixedWidth(width)

            # Apply styling based on sender
            if sender == "user":
                label.setStyleSheet("background-color: #228B22; border-radius: 10px; padding: 10px;")
                alignment = Qt.AlignRight
            else:
                label.setStyleSheet("background-color: #191970; border-radius: 10px; padding: 10px;")
                alignment = Qt.AlignLeft
        else:
            # If a widget is passed in, assume it's a QLabel or similar.
            label = text_or_widget
            # Make sure the sender property is set even in this branch.
            label.setProperty("sender", sender)
            alignment = Qt.AlignLeft  # or set differently if needed

        # Create a container for alignment
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.addWidget(label)
        layout.setAlignment(alignment)
        layout.setContentsMargins(0, 0, 0, 10)
        self.chatLayout.addWidget(container)

        # Adjust the sizes
        container.adjustSize()
        label.adjustSize()

    def save_current_chat_session(self):
        """Save the current chat session to a JSON file with sender information,
        but only if the chat space is not empty."""
        chat_history_dir = os.path.join(os.getcwd(), "chat_histories")
        os.makedirs(chat_history_dir, exist_ok=True)

        session_data = []
        for i in range(self.chatLayout.count()):
            container = self.chatLayout.itemAt(i).widget()
            if container:
                label = container.findChild(QLabel)
                if label:
                    sender = label.property("sender")
                    message_text = label.text()
                    session_data.append({"sender": sender, "message": message_text})

        # Do not save if there is no chat content.
        if not session_data:
            logging.info("Chat session is empty, nothing to save.")
            return

        # Determine the session file path.
        if self.current_session_file:
            session_path = self.current_session_file
        else:
            session_name = f"chat_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            session_path = os.path.join(chat_history_dir, session_name)
            self.current_session_file = session_path

        try:
            with open(session_path, "w", encoding="utf-8") as file:
                json.dump(session_data, file, indent=2)
            logging.info(f"Chat session saved as {session_path}")
            
            # Optionally, if the session is new, add it to the chat history list.
            session_file_name = os.path.basename(session_path)
            existing_items = [self.chatHistoryList.item(i).text() for i in range(self.chatHistoryList.count())]
            if session_file_name not in existing_items:
                self.chatHistoryList.addItem(session_file_name)
        except Exception as e:
            logging.error(f"Error saving chat session: {e}")
            QMessageBox.critical(self, "Save Error", f"Could not save chat session:\n{str(e)}")

    def load_existing_chat_sessions(self):
        """Load saved chat sessions into the chat history list."""
        chat_history_dir = os.path.join(os.getcwd(), "chat_histories")
        if not os.path.exists(chat_history_dir):
            return  # Nothing to load yet

        session_files = sorted(os.listdir(chat_history_dir))  # You can sort as needed
        self.chatHistoryList.clear()
        for session in session_files:
            file_name, ext = os.path.splitext(session)
            self.chatHistoryList.addItem(file_name)

    def load_chat_session(self, item):
        """Load a selected chat session from a JSON file into the chat layout."""
        session_name = item.text()
        session_name = session_name + ".json"
        chat_history_dir = os.path.join(os.getcwd(), "chat_histories")
        session_path = os.path.join(chat_history_dir, session_name)
        try:
            with open(session_path, "r", encoding="utf-8") as file:
                session_data = json.load(file)

            self.clear_chat_layout()

            # Re-add each message to the chat layout with the appropriate sender.
            for entry in session_data:
                sender = entry.get("sender", "model")
                message_text = entry.get("message", "")
                self.add_message(message_text, sender=sender)
            
            # Set the current session file so new messages are saved to the same file.
            self.current_session_file = session_path

        except Exception as e:
            logging.error(f"Error loading chat session {session_name}: {e}")
            QMessageBox.critical(self, "Load Error", f"Could not load chat session:\n{str(e)}")

    def clear_chat_layout(self):
        """Clear all messages from the chat layout."""
        while self.chatLayout.count():
            item = self.chatLayout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
                
    def new_chat_session(self):
        """Create a new chat session if the chat space is populated; do nothing if empty."""
        if self.chatLayout.count() > 0:
            logging.info("Chat space populated. Saving current session and creating a new chat session.")
            self.save_current_chat_session()  # Save the current session first.
            self.clear_chat_layout()            # Clear the chat area.
            self.current_session_file = None    # Reset so new messages start a new session.
        else:
            logging.info("Chat space is empty. No new session created.")

    def closeEvent(self, event):
        # Optionally prompt the user to save the current session
        self.save_current_chat_session()
        event.accept()

def load_stylesheet(file_path):
    """Load the stylesheet from a file."""
    logging.debug(f"Loading stylesheet from {file_path}")
    try:
        with open(file_path, "r") as file:
            return file.read()
    except Exception as e:
        logging.error(f"Error loading stylesheet: {e}")
        return ""


def main():
    logging.debug("Starting application")
    app = QApplication(sys.argv)
    stylesheet = load_stylesheet("resources/dark_mode.qss")
    app.setStyleSheet(stylesheet)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()