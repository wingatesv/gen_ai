import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QLabel, QFileDialog, QMessageBox, QMenu, QListWidgetItem
from PyQt5.QtCore import Qt  
from PyQt5.uic import loadUi
import os
import shutil
from llm_query import hugging_face_query

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Load the UI
        loadUi("resources/interface.ui", self)

        # Internal folder for storing documents
        self.internal_folder = os.path.join(os.getcwd(), "documents")
        os.makedirs(self.internal_folder, exist_ok=True)

        # Connect the upload button
        self.uploadButton.clicked.connect(self.upload_pdf)

        # Connect the send button
        self.sendButton.clicked.connect(self.send_query)

        # List to track uploaded files
        self.uploaded_files = []

        # Populate document list on startup
        self.update_document_list()

        # Enable right-click menu for document list
        self.documentList.setContextMenuPolicy(Qt.CustomContextMenu)
        self.documentList.customContextMenuRequested.connect(self.show_context_menu)

    def update_document_list(self):
        """Populate self.documentList with files from self.internal_folder."""
        # Clear the list widget and the uploaded files tracker
        self.documentList.clear()
        self.uploaded_files = []

        # Check for existing files in the internal folder
        for file_name in os.listdir(self.internal_folder):
            if file_name.endswith(".pdf"):  # Ensure only PDFs are added
                self.documentList.addItem(file_name)
                self.uploaded_files.append(file_name)

    def upload_pdf(self):
        # Open file dialog to select PDFs
        options = QFileDialog.Options()
        files, _ = QFileDialog.getOpenFileNames(
            self, 
            "Select PDF Documents", 
            "", 
            "PDF Files (*.pdf)", 
            options=options
        )
        if not files:
            return  # User canceled

        for file_path in files:
            file_name = os.path.basename(file_path)

            # Check if file already uploaded
            if file_name in self.uploaded_files:
                QMessageBox.warning(self, "Duplicate File", f"'{file_name}' is already uploaded.")
                continue

            # Copy the file to the internal folder
            dest_path = os.path.join(self.internal_folder, file_name)
            shutil.copy(file_path, dest_path)

            # Add to the list widget
            self.documentList.addItem(file_name)
            self.uploaded_files.append(file_name)

        QMessageBox.information(self, "Upload Successful", "PDF(s) uploaded successfully!")

    def show_context_menu(self, position):
        """Show context menu for the document list."""
        # Get the item under the cursor
        item = self.documentList.itemAt(position)
        if item:
            menu = QMenu()
            delete_action = menu.addAction("Delete File")
            action = menu.exec_(self.documentList.mapToGlobal(position))

            if action == delete_action:
                self.delete_file(item)

    def delete_file(self, item: QListWidgetItem):
        """Delete the selected file from the list and internal folder."""
        file_name = item.text()
        full_path = os.path.join(self.internal_folder, file_name)

        # Confirm deletion
        reply = QMessageBox.question(
            self, 
            "Delete File", 
            f"Are you sure you want to delete '{file_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                # Remove the file from the internal folder
                os.remove(full_path)

                # Remove the item from the list widget
                row = self.documentList.row(item)
                self.documentList.takeItem(row)
                self.uploaded_files.remove(file_name)

                QMessageBox.information(self, "Delete Successful", f"'{file_name}' has been deleted.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete '{file_name}'.\n{str(e)}")

    def send_query(self):
        # Logic to handle query and display chat
        user_input = self.promptInput.text()
        self.promptInput.clear()
        self.chatDisplay.append(f"User: {user_input}")
        # Add logic to process user_input and append model response
        # response = hugging_face_query(user_input)
        response = user_input
        self.chatDisplay.append(f"Model: {response}")
        

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()