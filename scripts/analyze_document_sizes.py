#!/usr/bin/env python3
"""Analyze document sizes in JSONL files to determine if chunking is needed."""

import json
import sys
from pathlib import Path
from collections import Counter

def analyze_file(file_path):
    """Analyze document word counts in a JSONL file."""
    if not file_path.exists():
        print(f"File not found: {file_path}")
        return

    word_counts = []

    print(f"\nAnalyzing {file_path.name}...")

    with open(file_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue

            doc = json.loads(line)
            text = doc.get('text', '')
            word_count = len(text.split())
            word_counts.append(word_count)

            # Show first few and any large ones
            if i < 5 or word_count > 5000:
                cite = doc.get('cite', 'unknown')
                title = doc.get('title', 'untitled')[:60]
                print(f"  [{i+1}] {cite}: {word_count:,} words - {title}")

    if not word_counts:
        print("  No documents found")
        return

    # Statistics
    total_docs = len(word_counts)
    min_words = min(word_counts)
    max_words = max(word_counts)
    avg_words = sum(word_counts) / len(word_counts)
    median_words = sorted(word_counts)[len(word_counts) // 2]

    # Count by size buckets
    over_6000 = sum(1 for w in word_counts if w > 6000)
    over_5000 = sum(1 for w in word_counts if w > 5000)
    over_3000 = sum(1 for w in word_counts if w > 3000)
    over_1000 = sum(1 for w in word_counts if w > 1000)

    print(f"\n  Statistics:")
    print(f"    Total documents: {total_docs:,}")
    print(f"    Min words: {min_words:,}")
    print(f"    Max words: {max_words:,}")
    print(f"    Average words: {avg_words:,.1f}")
    print(f"    Median words: {median_words:,}")
    print(f"\n  Distribution:")
    print(f"    > 6,000 words: {over_6000:,} docs ({over_6000/total_docs*100:.1f}%)")
    print(f"    > 5,000 words: {over_5000:,} docs ({over_5000/total_docs*100:.1f}%)")
    print(f"    > 3,000 words: {over_3000:,} docs ({over_3000/total_docs*100:.1f}%)")
    print(f"    > 1,000 words: {over_1000:,} docs ({over_1000/total_docs*100:.1f}%)")

    # Recommendation
    print(f"\n  Recommendation:")
    if over_6000 > 0:
        print(f"    ⚠ {over_6000} documents exceed 6,000 words - CHUNKING REQUIRED")
    elif over_5000 > 0:
        print(f"    ⚠ {over_5000} documents exceed 5,000 words - Consider chunking or truncation")
    else:
        print(f"    ✓ All documents under 5,000 words - Single embedding per document is feasible!")

def main():
    data_dir = Path("data")

    print("=" * 80)
    print("Document Size Analysis")
    print("=" * 80)

    files = [
        data_dir / "ga_code.jsonl",
        data_dir / "courtlistener_ga.jsonl",
        data_dir / "municode_gwinnett.jsonl",
    ]

    for file_path in files:
        analyze_file(file_path)

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
