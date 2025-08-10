from typing import List
import re
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

def split_sentences(text: str) -> List[str]:
    # naive sentence split
    s = re.split(r'(?<=[.!?])\s+', text.strip())
    return [seg.strip() for seg in s if seg.strip()]

def extractive_summary(text: str, num_sentences: int = 3) -> List[str]:
    sents = split_sentences(text)
    if len(sents) <= num_sentences:
        return sents
    vect = TfidfVectorizer(stop_words='english').fit_transform(sents)
    # score sentences by sum of TF-IDF values
    scores = np.asarray(vect.sum(axis=1)).ravel()
    idx = np.argsort(scores)[-num_sentences:][::-1]
    return [sents[i] for i in idx.tolist()]
