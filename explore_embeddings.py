#!/usr/bin/env python3
"""
Explore embeddings stored in SQLite database
"""

import sqlite3
import json
import numpy as np
import matplotlib.pyplot as plt
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
import pandas as pd

def explore_embeddings(db_path="podcast_index.db"):
    """Explore the embeddings in the database"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("🔍 Exploring Podcast Embeddings\n")
    
    # 1. Basic Statistics
    print("📊 Basic Statistics:")
    cursor.execute("SELECT COUNT(*) FROM podcasts")
    podcast_count = cursor.fetchone()[0]
    print(f"   Total podcasts: {podcast_count}")
    
    cursor.execute("SELECT COUNT(*) FROM chunks")
    chunk_count = cursor.fetchone()[0]
    print(f"   Total chunks: {chunk_count}")
    
    cursor.execute("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL")
    embedded_count = cursor.fetchone()[0]
    print(f"   Chunks with embeddings: {embedded_count}")
    
    if embedded_count == 0:
        print("\n❌ No embeddings found! Run indexing first.")
        conn.close()
        return
    
    # 2. Sample Embeddings
    print("\n📝 Sample Embeddings:")
    cursor.execute("""
        SELECT c.id, p.title, substr(c.content, 1, 100) as content_preview, 
               c.embedding
        FROM chunks c
        JOIN podcasts p ON c.podcast_id = p.id
        WHERE c.embedding IS NOT NULL
        LIMIT 3
    """)
    
    for chunk_id, title, content, embedding_json in cursor.fetchall():
        embedding = json.loads(embedding_json)
        print(f"\n   Chunk ID: {chunk_id}")
        print(f"   Podcast: {title}")
        print(f"   Content: {content}...")
        print(f"   Embedding dimensions: {len(embedding)}")
        print(f"   First 10 values: {embedding[:10]}")
        print(f"   Min value: {min(embedding):.4f}")
        print(f"   Max value: {max(embedding):.4f}")
        print(f"   Mean value: {np.mean(embedding):.4f}")
    
    # 3. Embedding Analysis
    print("\n📈 Embedding Analysis:")
    
    # Get all embeddings with metadata
    cursor.execute("""
        SELECT c.id, c.podcast_id, p.title, c.embedding
        FROM chunks c
        JOIN podcasts p ON c.podcast_id = p.id
        WHERE c.embedding IS NOT NULL
    """)
    
    data = []
    for chunk_id, podcast_id, title, embedding_json in cursor.fetchall():
        embedding = json.loads(embedding_json)
        data.append({
            'chunk_id': chunk_id,
            'podcast_id': podcast_id,
            'title': title,
            'embedding': embedding
        })
    
    # Convert to numpy array for analysis
    embeddings_matrix = np.array([d['embedding'] for d in data])
    print(f"   Embedding matrix shape: {embeddings_matrix.shape}")
    
    # Calculate statistics
    print(f"   Global min: {embeddings_matrix.min():.4f}")
    print(f"   Global max: {embeddings_matrix.max():.4f}")
    print(f"   Global mean: {embeddings_matrix.mean():.4f}")
    print(f"   Global std: {embeddings_matrix.std():.4f}")
    
    # 4. Similarity Analysis
    print("\n🔗 Similarity Analysis:")
    if len(data) >= 2:
        # Calculate similarities between first few chunks
        from podcast_semantic_search_complete import PodcastSemanticSearch
        search = PodcastSemanticSearch()
        
        for i in range(min(3, len(data))):
            for j in range(i+1, min(4, len(data))):
                sim = search.cosine_similarity(data[i]['embedding'], data[j]['embedding'])
                print(f"   Chunk {data[i]['chunk_id']} vs Chunk {data[j]['chunk_id']}: {sim:.4f}")
                if data[i]['podcast_id'] == data[j]['podcast_id']:
                    print(f"     (Same podcast: {data[i]['title']})")
                else:
                    print(f"     (Different podcasts)")
        
        search.close()
    
    # 5. Optional: Visualize embeddings (if not too many)
    if embedded_count <= 500:
        visualize = input("\n📊 Visualize embeddings? (y/n): ").strip().lower()
        if visualize == 'y':
            visualize_embeddings(embeddings_matrix, [d['title'] for d in data])
    
    conn.close()

def visualize_embeddings(embeddings, labels):
    """Create 2D visualization of embeddings using PCA and t-SNE"""
    print("\n🎨 Creating visualizations...")
    
    # PCA to 2D
    pca = PCA(n_components=2)
    embeddings_2d_pca = pca.fit_transform(embeddings)
    
    # Create figure
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # Plot PCA
    scatter = ax1.scatter(embeddings_2d_pca[:, 0], embeddings_2d_pca[:, 1], 
                         c=range(len(embeddings)), cmap='viridis', alpha=0.6)
    ax1.set_title('PCA Visualization of Embeddings')
    ax1.set_xlabel('First Principal Component')
    ax1.set_ylabel('Second Principal Component')
    
    # t-SNE (if not too many points)
    if len(embeddings) <= 200:
        print("   Computing t-SNE (this may take a moment)...")
        tsne = TSNE(n_components=2, random_state=42)
        embeddings_2d_tsne = tsne.fit_transform(embeddings)
        
        ax2.scatter(embeddings_2d_tsne[:, 0], embeddings_2d_tsne[:, 1], 
                   c=range(len(embeddings)), cmap='viridis', alpha=0.6)
        ax2.set_title('t-SNE Visualization of Embeddings')
        ax2.set_xlabel('t-SNE Component 1')
        ax2.set_ylabel('t-SNE Component 2')
    else:
        ax2.text(0.5, 0.5, 'Too many points for t-SNE\n(requires ≤200 points)', 
                ha='center', va='center', transform=ax2.transAxes)
        ax2.set_title('t-SNE Visualization')
    
    plt.tight_layout()
    plt.savefig('embeddings_visualization.png', dpi=150)
    print("   ✓ Saved visualization to embeddings_visualization.png")
    plt.show()

def export_embeddings_to_csv(db_path="podcast_index.db", output_file="embeddings_export.csv"):
    """Export embeddings data to CSV for external analysis"""
    conn = sqlite3.connect(db_path)
    
    query = """
        SELECT 
            c.id as chunk_id,
            c.podcast_id,
            p.filename,
            p.title as podcast_title,
            c.chunk_index,
            substr(c.content, 1, 200) as content_preview,
            length(c.embedding) as embedding_size
        FROM chunks c
        JOIN podcasts p ON c.podcast_id = p.id
        WHERE c.embedding IS NOT NULL
    """
    
    df = pd.read_sql_query(query, conn)
    df.to_csv(output_file, index=False)
    print(f"\n✓ Exported {len(df)} embedded chunks to {output_file}")
    
    conn.close()

if __name__ == "__main__":
    # Main exploration
    explore_embeddings()
    
    # Optional: Export to CSV
    export_choice = input("\n📄 Export embeddings metadata to CSV? (y/n): ").strip().lower()
    if export_choice == 'y':
        export_embeddings_to_csv()