#!/usr/bin/env python3
"""
Create a Travel Planner test scenario to match your desired output format
"""

import urllib.request
import urllib.parse
import json
import sys

BASE_URL = "http://localhost:8080"

def make_request(url, data=None, method="GET"):
    """Make HTTP request using urllib"""
    try:
        if data:
            data = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            req.get_method = lambda: method
        else:
            req = urllib.request.Request(url)
            
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Request failed: {e}")
        return None

def display_formatted_result(result):
    """Display the JSON result in your desired tabular format"""
    
    if "persona_analysis" not in result:
        print("❌ Invalid result format")
        return
    
    analysis = result["persona_analysis"]
    
    print("\n" + "="*80)
    print("📋 TRAVEL PLANNER OUTPUT (Your Desired Format)")
    print("="*80)
    
    # METADATA Section
    print("\nmetadata")
    metadata = analysis.get("metadata", {})
    
    print("input_documents")
    for i, doc in enumerate(metadata.get("input_documents", [])):
        print(f"{i}\t\"{doc}\"")
    
    print(f"persona\t\"{metadata.get('persona', 'Unknown')}\"")
    print(f"job_to_be_done\t\"{metadata.get('job_to_be_done', 'Unknown')}\"")
    print(f"processing_timestamp\t\"{metadata.get('processing_timestamp', 'Unknown')}\"")
    
    # EXTRACTED SECTIONS
    print("\nextracted_sections")
    for i, section in enumerate(analysis.get("extracted_sections", [])):
        print(f"{i}")
        print(f"document\t\"{section.get('document', 'Unknown')}\"")
        print(f"section_title\t\"{section.get('section_title', 'Untitled Section')}\"")
        print(f"importance_rank\t{section.get('importance_rank', 0)}")
        print(f"page_number\t{section.get('page_number', 0)}")
    
    # SUBSECTION ANALYSIS
    print("\nsubsection_analysis")
    for i, subsection in enumerate(analysis.get("subsection_analysis", [])):
        print(f"{i}")
        print(f"document\t\"{subsection.get('document', 'Unknown')}\"")
        refined_text = subsection.get('refined_text', '')
        # Limit text length for display
        if len(refined_text) > 200:
            refined_text = refined_text[:197] + "..."
        print(f"refined_text\t\"{refined_text}\"")
        print(f"page_number\t{subsection.get('page_number', 0)}")
    
    print("\n" + "="*80)

# Test 1: Travel Planner Persona 
print("🌍 TESTING TRAVEL PLANNER PERSONA (Like South of France)")
print("=" * 60)

docs_response = make_request(f"{BASE_URL}/api/persona-analyze/available-docs")

if docs_response:
    available_docs = [doc["doc_id"] for doc in docs_response["available_documents"]]
    print(f"✅ Found {len(available_docs)} documents")
    
    # Test with Travel Planner (similar to your example)
    travel_request = {
        "doc_ids": available_docs[:4],  # Use 4 documents like your example
        "persona": {
            "role": "Travel Planner"
        },
        "job_to_be_done": {
            "task": "Plan a trip of 4 days for a group of 10 college friends"
        },
        "job_description": "I need to plan a comprehensive 4-day trip for a group of 10 college friends. Looking for destination information, activities, accommodation options, dining recommendations, and practical travel tips.",
        "chunk_size": 350
    }
    
    print("📡 Sending Travel Planner analysis request...")
    result = make_request(f"{BASE_URL}/api/persona-analyze", travel_request, "POST")
    
    if result:
        print("✅ SUCCESS! Travel planner analysis completed!")
        print(f"⏱️  Processing time: {result.get('processing_time', 'N/A')} seconds")
        print(f"📊 Relevant sections: {result.get('relevant_sections', 'N/A')}")
        
        # Display formatted result
        display_formatted_result(result)
        
        # Save result
        with open("travel_planner_formatted.json", "w") as f:
            json.dump(result, f, indent=2)
        print(f"\n💾 Full result saved to 'travel_planner_formatted.json'")
        
    else:
        print("❌ Travel planner analysis failed")

else:
    print("❌ Could not get available documents")

# Test 2: Business Consultant Persona 
print(f"\n{'='*60}")
print("💼 TESTING BUSINESS CONSULTANT PERSONA")
print("=" * 60)

if docs_response:
    business_request = {
        "doc_ids": available_docs[:3],
        "persona": {
            "role": "Business Consultant"
        },
        "job_to_be_done": {
            "task": "Analyze business strategies and organizational planning"
        },
        "job_description": "I need to understand business planning methodologies, organizational structures, and strategic implementation approaches for consulting projects.",
        "chunk_size": 400
    }
    
    print("📡 Sending Business Consultant analysis request...")
    result = make_request(f"{BASE_URL}/api/persona-analyze", business_request, "POST")
    
    if result:
        print("✅ SUCCESS! Business consultant analysis completed!")
        print(f"⏱️  Processing time: {result.get('processing_time', 'N/A')} seconds")
        
        # Display formatted result  
        display_formatted_result(result)
        
        # Save result
        with open("business_consultant_formatted.json", "w") as f:
            json.dump(result, f, indent=2)
        print(f"\n💾 Business result saved to 'business_consultant_formatted.json'")
        
    else:
        print("❌ Business consultant analysis failed")

print("\n🎉 All persona tests completed!")
