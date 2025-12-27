import json
import re
import umap
import hdbscan
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import pickle

class Clusterer():
    """
    This is a class that is written to cluster a given amount of input texts.
    It applies a pipeline as:
    - Take json input
    - Clear it
    - Embed it
    - Reduce it.
    - Cluster it.

    A user can basically call fit function with path of the json file after creating an object.
    It can be tested via model_test with a single string input of a topic.


    NOTE: Input format of training data must be:
            [{abstract: text}, {abstract: text}] and so on.
    """


    def __init__(self, 
                 embedder_model='all-MiniLM-L6-v2', 
                 umap_n_neighbors=15, 
                 umap_n_components=5,
                 min_cluster_size=20,
                 min_samples=1
                 ):
        self.data = []
        self.embedded = []
        self.data_clusters = []
        self.clustered_data = {}
        
        self.embedder_model = SentenceTransformer(embedder_model)
        self.reducer_model = umap.UMAP(n_neighbors=umap_n_neighbors, 
                                      n_components=umap_n_components, 
                                      metric='cosine', 
                                      random_state=42)
        self.clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, 
                                         min_samples=min_samples)

    def _clear_input(self, inp_text):
        
        text = str(inp_text).lower()    
        text = re.sub(r'[^a-zçğıöşü\s]', ' ', text)
        doc = " ".join(text.split())        
        return doc

    def _upload_input(self, path):
        with open(path, "r") as f:
            data = json.load(f)
        
        for o in data:
            abstract_content = o.get("abstract")
            if abstract_content and str(abstract_content).strip().lower() != "null":
                self.data.append(self._clear_input(o))
            else:
                print("There is an abstract with null input!")
    def _embed_data(self):
        
        self.embedded = self.embedder_model.encode(self.data)

    def _reducer(self):
        
        self.embedded = self.reducer_model.fit_transform(self.embedded)
    
    def _cluster(self):
        
        self.data_clusters = self.clusterer.fit_predict(self.embedded)
    
    def _index_input(self):
        self.clustered_data = {} 
        
        for i in range(len(self.data)):
            cluster_id = self.data_clusters[i]
            
            if cluster_id not in self.clustered_data:
                self.clustered_data[cluster_id] = []
        
            self.clustered_data[cluster_id].append(self.data[i])
        
    def fit(self, path):

    
        print("Loading data...")
        self._upload_input(path)
        print("Embedding data...")
        self._embed_data()        
        print("Reducing dimensions...")
        self._reducer()           
        print("Clustering...")
        self._cluster()
        print("Indexing results...")
        self._index_input()          
        
        n_clusters = len(set(self.data_clusters)) - (1 if -1 in self.data_clusters else 0)
        print(f"Done! Found {n_clusters} clusters.")
    


    def save_state(self, filename="search_engine.pkl"):
        """Saves the trained models and indexed data to a file."""
        state = {
            "reducer": self.reducer_model,
            "clusters": self.data_clusters,
            "clustered_data": self.clustered_data,
            "embedded_384": self.embedded, # Keep for the similarity fix
        }
        with open(filename, "wb") as f:
            pickle.dump(state, f)
        print(f"Engine state saved to {filename}")

    def load_state(self, filename="search_engine.pkl"):
        """Loads everything back so you can search immediately."""
        with open(filename, "rb") as f:
            state = pickle.load(f)
        
        self.reducer_model = state["reducer"]
        self.data_clusters = state["clusters"]
        self.clustered_data = state["clustered_data"]
        self.embedded = state["embedded_384"]
        print("Engine state loaded. Ready for rapid search.")

    def test_model(self, query_text):
        
        
        query_cleaned = self._clear_input(query_text)
        query_vec_384 = self.embedder_model.encode([query_cleaned])
        
        query_vec_5d = self.reducer_model.transform(query_vec_384)

        unique_labels = [l for l in set(self.data_clusters) if l != -1]
        
        if not unique_labels:
            return self.clustered_data.get(-1, [])

        best_cluster = -1
        max_sim = -1

        for label in unique_labels:
            
            indices = np.where(self.data_clusters == label)[0]
            
            cluster_vectors = self.embedded[indices]
            
            centroid = np.mean(cluster_vectors, axis=0).reshape(1, -1)
            
            similarity = cosine_similarity(query_vec_5d, centroid)[0][0]
            
            if similarity > max_sim:
                max_sim = similarity
                best_cluster = label
        
        return self.clustered_data.get(best_cluster, []), max_sim
    

