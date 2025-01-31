import sys
import os
import shutil
import time
import yaml
from concurrent.futures import ThreadPoolExecutor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QFileDialog, QMessageBox, QMenu, QWidget, QHBoxLayout, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.uic import loadUi
from llm_query import initialize_rag, hugging_face_query


class MainWindow(QMainWindow):
    response_ready = pyqtSignal(str)

    def __init__(self):
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

        # initialize RAG
        initialize_rag(
            api_token=self.api_token,
            embedding_model=self.embedding_model,
            llm_model=self.llm_model,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap
        )

        # Signals and UI setup
        self.response_ready.connect(self.handle_response)
        self.uploadButton.clicked.connect(self.upload_pdf)
        self.sendButton.clicked.connect(self.send_query)
        self.documentList.setContextMenuPolicy(Qt.CustomContextMenu)
        self.documentList.customContextMenuRequested.connect(self.show_context_menu)
        self.splitter.setSizes([200, self.width() - 200])

        # Internal state
        self.internal_folder = self._setup_internal_folder("documents")
        self.uploaded_files = []
        self.update_document_list()

    @staticmethod
    def load_config(config_path):
        """Load configuration from a YAML file."""
        if not os.path.exists(config_path):
            QMessageBox.critical(None, "Configuration Error", f"Missing configuration file: {config_path}")
            sys.exit(1)
        
        try:
            with open(config_path, "r") as file:
                return yaml.safe_load(file)
        except Exception as e:
            QMessageBox.critical(None, "Configuration Error", f"Failed to read config file:\n{str(e)}")
            sys.exit(1)

    @staticmethod
    def _setup_internal_folder(folder_name):
        """Create and return the internal folder path."""
        folder_path = os.path.join(os.getcwd(), folder_name)
        os.makedirs(folder_path, exist_ok=True)
        return folder_path

    def update_document_list(self):
        """Populate the document list with files from the internal folder."""
        self.documentList.clear()
        self.uploaded_files = [
            file for file in os.listdir(self.internal_folder) if file.endswith(".pdf")
        ]
        self.documentList.addItems(self.uploaded_files)

    def upload_pdf(self):
        """Handle file upload and update the RAG database."""
        files, _ = QFileDialog.getOpenFileNames(self, "Select PDF Documents", "", "PDF Files (*.pdf)")
        if not files:
            return

        new_files = []  # Track new files that are added

        for file_path in files:
            file_name = os.path.basename(file_path)
            if file_name in self.uploaded_files:
                QMessageBox.warning(self, "Duplicate File", f"'{file_name}' is already uploaded.")
                continue  # Skip duplicate files

            shutil.copy(file_path, os.path.join(self.internal_folder, file_name))
            self.uploaded_files.append(file_name)
            self.documentList.addItem(file_name)
            new_files.append(file_name)  # Add to list of new files

        if new_files:
            QMessageBox.information(self, "Upload Successful", "PDF(s) uploaded successfully!")

            # **Update RAG Database After Upload**
            self.update_rag(new_files)

    def update_rag(self, new_files):
        """Update the RAG database to include the newly uploaded files."""
        print(f"Updating RAG with {len(new_files)} new file(s)...")
        initialize_rag(
            api_token=self.api_token,
            embedding_model=self.embedding_model,
            llm_model=self.llm_model,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap
        )
        print("RAG update completed!")
        
    def show_context_menu(self, position):
        """Show context menu for the document list."""
        item = self.documentList.itemAt(position)
        if item:
            menu = QMenu()
            delete_action = menu.addAction("Delete File")
            if menu.exec_(self.documentList.mapToGlobal(position)) == delete_action:
                self.delete_file(item)

    def delete_file(self, item):
        """Delete the selected file."""
        file_name = item.text()
        file_path = os.path.join(self.internal_folder, file_name)

        if QMessageBox.question(
            self, "Delete File", f"Are you sure you want to delete '{file_name}'?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            try:
                os.remove(file_path)
                self.documentList.takeItem(self.documentList.row(item))
                self.uploaded_files.remove(file_name)
                QMessageBox.information(self, "Delete Successful", f"'{file_name}' has been deleted.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete '{file_name}'.\n{str(e)}")

    def show_dot_animation(self):
        """Show a loading animation while waiting for the response."""
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
        if hasattr(self, "dot_timer"):
            self.dot_timer.stop()
        if hasattr(self, "dot_label"):
            self.chatLayout.removeWidget(self.dot_label)
            self.dot_label.deleteLater()

    def send_query(self):
        """Send a query to the LLM and handle the response."""
        user_input = self.promptInput.text().strip()
        if not user_input:
            return

        self.add_message(user_input, sender="user")
        self.promptInput.clear()
        self.show_dot_animation()

        def query_llm():
            return str(hugging_face_query(user_input))

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(query_llm)
        future.add_done_callback(lambda f: self.response_ready.emit(f.result()))

    def handle_response(self, response):
        """Handle the response from the LLM."""
        self.remove_dot_animation()
        self.add_message(response, sender="model")

    def add_message(self, text_or_widget, sender):
        """Add a message bubble or widget to the chat layout."""
        if isinstance(text_or_widget, str):
            # Create a QLabel for text
            label = QLabel(text_or_widget)
            label.setWordWrap(True)  # Enable word wrapping
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

            # Dynamically adjust the label's width based on text
            font_metrics = label.fontMetrics()
            text_width = font_metrics.boundingRect(text_or_widget).width()
            max_width = 400  # Maximum width for the label
            width = min(text_width + 20, max_width)  # Add padding and constrain width
            label.setFixedWidth(width)

            # Apply styling based on sender
            label.setStyleSheet(
                "background-color: #228B22; border-radius: 10px; padding: 10px;" if sender == "user" else
                "background-color: #191970; border-radius: 10px; padding: 10px;"
            )
            alignment = Qt.AlignRight if sender == "user" else Qt.AlignLeft
        else:
            # Custom widget
            label = text_or_widget
            alignment = Qt.AlignLeft

        # Create a container for alignment
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.addWidget(label)
        layout.setAlignment(alignment)
        layout.setContentsMargins(0, 0, 0, 10)
        self.chatLayout.addWidget(container)

        # Ensure the label resizes dynamically
        container.adjustSize()
        label.adjustSize()


def load_stylesheet(file_path):
    """Load the stylesheet from a file."""
    try:
        with open(file_path, "r") as file:
            return file.read()
    except Exception as e:
        print(f"Error loading stylesheet: {e}")
        return ""


def main():
    app = QApplication(sys.argv)
    stylesheet = load_stylesheet("resources/dark_mode.qss")
    app.setStyleSheet(stylesheet)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()