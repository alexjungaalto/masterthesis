#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Aug 12 14:07:43 2023

@author: alexanderjung
"""

import re

def extract_sections_and_labels(tex_file_path):
    with open(tex_file_path, 'r') as tex_file:
        tex_content = tex_file.read()

    section_pattern = r'\\section\{(.+?)\}\s*\\label\{(.+?)\}'
    subsection_pattern = r'\\subsection\{(.+?)\}\s*\\label\{(.+?)\}'
    # Add more patterns for other sectioning commands if needed

    section_matches = re.findall(section_pattern, tex_content)
    subsection_matches = re.findall(subsection_pattern, tex_content)

    sections_and_labels = section_matches + subsection_matches
    return sections_and_labels

def find_parent_section(tex_content, label):
    section_pattern = r'\\section\{(.+?)\}\s*\\label\{(' + re.escape(label) + r')\}'
    subsection_pattern = r'\\subsection\{(.+?)\}\s*\\label\{(' + re.escape(label) + r')\}'
    # Add more patterns for other sectioning commands if needed

    section_match = re.search(section_pattern, tex_content)
    subsection_match = re.search(subsection_pattern, tex_content)

    if section_match:
        return "Section: " + section_match.group(1)
    elif subsection_match:
        return "Subsection: " + subsection_match.group(1)
    else:
        return "Parent section not found"

def analyze_refs(tex_file_path):
    with open(tex_file_path, 'r') as tex_file:
        tex_content = tex_file.read()

    ref_pattern = r'\\ref\{(.+?)\}'
    ref_labels = re.findall(ref_pattern, tex_content)

    for label in ref_labels:
        parent_section = find_parent_section(tex_content, label)
        print(f"Reference Label: {label}, Parent Section: {parent_section}")
        
def extract_refs(tex_content):
    ref_pattern = r'\\ref\{(.+?)\}'
    ref_labels = re.findall(ref_pattern, tex_content)
    return ref_labels

def iterate_over_refs(tex_file_path):
    with open(tex_file_path, 'r') as tex_file:
        tex_content = tex_file.read()

    ref_labels = extract_refs(tex_content)

    for label in ref_labels:
        print(f"Referenced Label: {label}")



tex_file_path = 'test.tex'
sections_and_labels = extract_sections_and_labels(tex_file_path)

for section_name, label in sections_and_labels:
    print(f"Section Name: {section_name}, Label: {label}")

# Read the LaTeX file
with open('test.tex', 'r') as f:
    tex_content = f.read()

# Find the first occurrence of \eqref{}
eqref_match = re.search(r'\\eqref\{.*?\}', tex_content)

if eqref_match:
    print("equref",eqref_match.group())
    eqref_position = eqref_match.start()
    
    # Search for the previous \section{} before \eqref{}
    section_match = re.search(r'\\section\{(.*?)\}', tex_content[:eqref_position], re.DOTALL | re.MULTILINE)
    
    if section_match:
        previous_section_label = section_match.group(1)
        print("Label of the Previous Section:", previous_section_label)
    else:
        print("No previous section found before \\eqref{}.")
else:
    print("No \\eqref{} found in the LaTeX file.")
    
    
with open('test.tex', 'r') as f:
    tex_content = f.read()

# Find all occurrences of \section{}
section_matches = re.finditer(r'\\section\{(.*?)\}', tex_content, re.DOTALL | re.MULTILINE)

# Collect the locations and labels of all sections
sections = []
for match in section_matches:
    section_label = match.group(1)
    section_location = match.start()
    sections.append((section_label, section_location))

# Print the locations and labels of all sections
for section in sections:
    print(f"Section Label: {section[0]}\nLocation: {section[1]}\n")

text_file = open("Output.txt", "w")

text_file.write(tex_content[sections[-6][1]:sections[-5][1]])

text_file.close()

