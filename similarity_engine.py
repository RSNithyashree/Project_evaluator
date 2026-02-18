from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

def calculate_similarity(new_text, old_projects):
    """
    Compares new project text with old texts.
    Returns: (max_percentage, match_index)
    """

    # If no previous projects, return 0% and no index
    if not old_projects or len(old_projects) == 0:
        return 0.0, None

    try:
        # Combine new text (index 0) with old project texts (index 1 onwards)
        documents = [new_text] + old_projects

        # Convert text to TF-IDF vectors
        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf_matrix = vectorizer.fit_transform(documents)

        # Calculate cosine similarity matrix
        # This compares every document with every other document
        similarity_matrix = cosine_similarity(tfidf_matrix)

        # We only care about the similarities of our new document (row 0)
        # We skip index 0 because that is the new document comparing to itself (always 1.0)
        similarities = similarity_matrix[0][1:]

        if len(similarities) == 0:
            return 0.0, None

        # 1. Get highest similarity score
        max_similarity = np.max(similarities)

        # 2. Get the INDEX of that highest similarity
        # This index corresponds to the position in the 'old_projects' list
        match_index = np.argmax(similarities)

        # Convert to percentage
        percentage = round(float(max_similarity) * 100, 2)

        return percentage, int(match_index)

    except Exception as e:
        print("❌ Similarity calculation error:", e)
        return 0.0, None