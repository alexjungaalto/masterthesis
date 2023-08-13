#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Aug 12 14:07:43 2023

@author: alexanderjung
"""

import re



# replace 'test.tex' with the filename of your file 

filename = 'test.tex'

# Define the regular expressions to match chapters, sections, and subsections
chapter_pattern = r'\\chapter\{(.+?)\}\s*\\label\{(.+?)\}'
section_pattern = r'\\section\{(.+?)\}\s*\\label\{(.+?)\}'
subsection_pattern = r'\\subsection\{(.+?)\}\s*\\label\{(.+?)\}'

# Read the .tex file
with open(filename, 'r') as tex_file:
    tex_content = tex_file.read()

# Search for occurrences of chapters, sections, and subsections
chapter_matches = re.finditer(chapter_pattern, tex_content)
section_matches = re.finditer(section_pattern, tex_content)
subsection_matches = re.finditer(subsection_pattern, tex_content)

print("*********\n")
# Store the extracted information in a list of dictionaries
occurrences = []
#for match in chapter_matches:
#    occurrences.append({'type': 'chapter', 'name': match[0], 'label': match[1]})
for match in section_matches:
    print()
    occurrences.append({'type': 'section', 'name': match.groups()[0], 'label': match.groups()[1], 'location':match.start()})
for match in subsection_matches:
    occurrences.append({'type': 'subsection', 'name': match.groups()[0], 'label': match.groups()[1], 'location':match.start()})


occurrences.append({'type': 'end of file', 'name': "end of file", 'label': "eof", 'location':len(tex_content)})

# Print the stored information
for occurrence in occurrences:
    print(f"Type: {occurrence['type']}, Name: {occurrence['name']}, Label: {occurrence['label']}, location: {occurrence['location']}")

import pandas as pd 

df = pd.DataFrame.from_dict(occurrences).sort_values(by=['location'])



#print(df[['label','location']])

import networkx as nx

# start with an empty graph 
G = nx.DiGraph()


# add a separate node to the graph G for each chapter, section and subsection.  

for ind in df.index[:-1]:
  #  if ind < (len(df.index)-1): 
    G.add_node(ind,label = df['label'][ind],startpos=df['location'][ind],endpos=df['location'][df.index[ind+1]])
    print("idx :",ind,df['label'][ind], df['location'][ind])
    
# add a directed edge from node "a" to node "b" if there is a \ref{} in the chapter/section/subection 
# "a" to the chatper/section/subsection "b" 

for startnode in G.nodes(): 
    for endnode in G.nodes():
        # check if there is a ref in the chapter/section/subsection "startnode" to the 
        # chapter/section/subsection "endnode" 
        pattern = r'\\ref\{' + re.escape(G.nodes[endnode]["label"]) + r'\}'
        nrlinks = len(re.findall(pattern,tex_content[G.nodes[startnode]["startpos"]:G.nodes[startnode]["endpos"]]))
        print("there are ", nrlinks, "refs from ",G.nodes[startnode]["label"],"to ",G.nodes[endnode]["label"])
        if nrlinks > 0 : 
            G.add_edge(startnode,endnode,weight=nrlinks)
        print(pattern)  
        
   
pos=nx.spring_layout(G) 
nx.draw(G,pos,labels=nx.get_node_attributes(G, "label"))
labels = nx.get_edge_attributes(G,'weight')
nx.draw_networkx_edge_labels(G,pos,edge_labels=labels)

nx.write_latex(G, "my_figure.tex", pos = pos, caption="Structure of "+filename, latex_label="fig1")


