from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def normalize_scores(scores):
    min_score, max_score = min(scores), max(scores)
    if max_score == min_score:
        return [0.5] * len(scores)  # fallback if all scores are equal
    return [(s - min_score) / (max_score - min_score) for s in scores]


import re

def trim_to_sentence(text, limit=800):
    sents = re.split(r'(?<=[.!?])\s+', text.strip())
    refined = []
    total = 0
    for s in sents:
        if total + len(s) > limit:
            break
        refined.append(s)
        total += len(s)
    return " ".join(refined).strip()

    # """
    # Trim text to complete sentences under limit (default 800 chars)
    # """
    # text = text.strip()
    # if len(text) <= limit:
    #     return text
    # trimmed = text[:limit]
    # last_period = trimmed.rfind(". ")
    # return trimmed[:last_period + 1].strip() if last_period > 0 else trimmed.strip()


def rank_chunks(chunks, job_description, persona, job_to_be_done):
    """
    Rank fine-grained chunks by relevance to job description.
    Returns top 5 chunks + formatted refined_texts.
    """
    if not chunks:
        return [], []
    context = f"{persona['role']} needs to {job_to_be_done['task']}"  # Construct from inputs
    combined_prompt = context + ". " + job_description
    corpus = [combined_prompt] + [chunk["text"] for chunk in chunks]

    # corpus = [job_description] + [chunk["text"] for chunk in chunks]
    vectorizer = TfidfVectorizer(stop_words="english", max_features=1000, ngram_range=(1, 2))
    tfidf = vectorizer.fit_transform(corpus)

    scores = (tfidf[0] @ tfidf[1:].T).toarray()[0]
    norm_scores = normalize_scores(scores)

    for i, score in enumerate(norm_scores):
        boost = 0.05 if chunks[i]["page_number"] <= 2 else 0.0
        chunks[i]["score"] = round(score + boost, 4)

    # Deduplicate by (document, title)
    seen = set()
    top_chunks = []
    for chunk in sorted(chunks, key=lambda x: x["score"], reverse=True):
        key = (chunk["document"], chunk["title"])
        if key not in seen:
            top_chunks.append(chunk)
            seen.add(key)
        if len(top_chunks) >= 5:
            break

    refined_texts = []
    for chunk in top_chunks:
        refined_texts.append({
            "document": chunk["document"],
            "refined_text": trim_to_sentence(chunk["text"]),
            "page_number": chunk["page_number"],
            "title": chunk["title"],
            "relevance_score": chunk["score"]
        })

    return top_chunks, refined_texts


def rank_chunks_with_sections(chunks, job_description):
    """
    Rank by section (document + heading) instead of individual chunks.
    Aggregates chunks per section and scores.
    """
    sections = {}
    for chunk in chunks:
        key = f"{chunk['document']}::{chunk['title']}"
        if key not in sections:
            sections[key] = {
                "document": chunk["document"],
                "title": chunk["title"],
                "page_number": chunk["page_number"],
                "text": "",
                "chunks": []
            }
        sections[key]["text"] += " " + chunk["text"]
        sections[key]["chunks"].append(chunk)

    section_list = list(sections.values())
    corpus = [job_description] + [section["text"] for section in section_list]

    vectorizer = TfidfVectorizer(stop_words="english", max_features=1000, ngram_range=(1, 2))
    tfidf = vectorizer.fit_transform(corpus)

    scores = (tfidf[0] @ tfidf[1:].T).toarray()[0]
    norm_scores = normalize_scores(scores)

    for i, score in enumerate(norm_scores):
        boost = 0.05 if section_list[i]["page_number"] <= 2 else 0.0
        section_list[i]["score"] = round(score + boost, 4)

    top_sections = sorted(section_list, key=lambda x: x["score"], reverse=True)[:5]

    refined_texts = []
    for section in top_sections:
        refined_texts.append({
            "document": section["document"],
            "refined_text": trim_to_sentence(section["text"]),
            "page_number": section["page_number"],
            "title": section["title"],
            "relevance_score": section["score"]
        })

    return top_sections, refined_texts
# Updated on 2:42 111 lines