# builder.py

def build_output_json(input_documents, persona, job_to_be_done, ranked_sections, refined_texts, timestamp):
    # Format persona and job_to_be_done as strings for cleaner output
    persona_str = persona.get("role", "Unknown Role") if isinstance(persona, dict) else str(persona)
    job_str = job_to_be_done.get("task", "Unknown Task") if isinstance(job_to_be_done, dict) else str(job_to_be_done)
    
    # If job_to_be_done has more detail, create a comprehensive description
    if isinstance(job_to_be_done, dict) and job_to_be_done.get("goal"):
        job_str = f"{job_to_be_done.get('task', '')} - {job_to_be_done.get('goal', '')}"
    
    return {
        "metadata": {
            "input_documents": input_documents,
            "persona": persona_str,
            "job_to_be_done": job_str,
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
                "refined_text": chunk["refined_text"],
                "page_number": chunk["page_number"]
            }
            for chunk in refined_texts
        ]
    }