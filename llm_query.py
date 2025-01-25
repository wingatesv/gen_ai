from llama_index.llms.huggingface_api import HuggingFaceInferenceAPI
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings, StorageContext
from llama_index.embeddings.huggingface_api import HuggingFaceInferenceAPIEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core.node_parser import SentenceSplitter

import chromadb


API_TOKEN = ""
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
LLM_MODEL = "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B"
COLLECTION_NAME = "doc"

def hugging_face_query(prompt):
    try:
        # Initialize Chroma client
        chroma_client = chromadb.Client()

        # Create or retrieve a collection
        chroma_collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)

        # Set up the ChromaVectorStore
        vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

        # Create a StorageContext
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        # Load documents
        documents = SimpleDirectoryReader("documents").load_data()

        text_splitter = SentenceSplitter(chunk_size=512, chunk_overlap=10)
        

        # Set up Hugging Face embedding model using cloud API
        Settings.embed_model = HuggingFaceInferenceAPIEmbedding(
            model_name=EMBEDDING_MODEL, 
            token=API_TOKEN,
        )

        # Set up Hugging Face LLM via Inference API
        Settings.llm = HuggingFaceInferenceAPI(
            model_name=LLM_MODEL,
            token=API_TOKEN,
        )

        Settings.chunk_size = 512
        Settings.text_splitter = text_splitter



        # Build the index with the documents
        index = VectorStoreIndex.from_documents(documents, storage_context=storage_context, transformations=[text_splitter])

        # Query the index
        query_engine = index.as_query_engine()
        response = query_engine.query(prompt)

        return response



    except Exception as e:
        error_message  = f"Error querying Hugging Face API: {e}"
        return error_message

if __name__ == "__main__":
    # Test prompt
    prompt = "What is product marketing mix"
    hugging_face_query(prompt)

  
