# builder.py

def build_output_json(input_documents, persona, job_to_be_done, ranked_sections, refined_texts, timestamp):
    return {
        "metadata": {
            "input_documents": input_documents,
            "persona": persona,
            "job_to_be_done": job_to_be_done,
            "processing_timestamp": timestamp
        },
        "extracted_sections": [
            {
                "document": chunk["document"],
                "section_title": chunk.get("title", "Untitled Section"),
                "importance_rank": i + 1,
                "page_number": chunk["page_number"]
            }
            for i, chunk in enumerate(ranked_sections)
        ],
        "subsection_analysis": [
            {
                "document": chunk["document"],
                "refined_text": chunk["refined_text"],  # <-- changed from chunk["text"]
                "page_number": chunk["page_number"]
            }
            for chunk in refined_texts
        ]
    }