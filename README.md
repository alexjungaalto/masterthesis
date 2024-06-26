# Doing a Master Thesis on Applied Machine Learning 

Do you have some topic, application or research question that you would like to explore during a master thesis? 
If you think that machine learning methods could be useful for your thesis you might consider having [me]
(https://alexjungaalto.github.io/) as your thesis supervisor. 

# What can you expect from me as your thesis supervisor ?

My main expertise is on the statistical and computational aspects of machine learning (ML) from network-structured data. 
Networked-data arises in many important application domains and provides a rich mathematical structure that can be exploited 
for the training of ML models. Our recent work includes [this paper](https://arxiv.org/abs/2105.12769) and <a href="https://ieeexplore.ieee.org/document/9298875" target="__blank">that paper</a>. 

Another recent focus of my research is the application of information theory to explainable ML. We have introduced a quantitative measure 
for the subjective explainability of predictions <a href="https://ieeexplore.ieee.org/document/9089200" target="__blank">in this paper</a>
and used it to regularize the training of any given ML model  <a href="https://arxiv.org/abs/2009.01492" target="_blank">in this paper</a>. 

Besides the above research threads, I am always eager to learn about novel and important applications of ML techniques. 
I am happy to help you in making good use of existing ML methods or develop novel techniques that are tailored to your specific topic. 

If you choose to work with me as your supervisor, I will add you to our group mailing list so that you 
receive invitations to our regular group meetings ([YouTube Playlist](https://www.youtube.com/playlist?list=PLrbn2dGrLJK8wsi_vpr94Gzas7TzUsFNh)). 
During these meetings, you can present your work, seek feedback from other group members and also see what 
they are working on. Note that I will ask for your explicit consent before sharing any recording of you on my Youtube. 
I will also add you to our discussion forum (currently using [Slack](https://slack.com/)) where you can ask questions 
and look for help. 

# The Start 

In general, the beginning of your thesis work is the formulation of your topic as a ML problem. This formulation amounts to 
explaining (the meaning of) data points, their features and label ([see this video](https://youtu.be/2q5jpvD-638)). You should 
also think about one or two potential ML models that you are familiar with (e.g., you can implement them using a programming 
language such as Python). Beside the choice of data and model, you should also think about possible performance criteria or 
loss functions that are used to evaluate the usefulness of a (trained) model. 

You can read more about these design choices (for data, model and loss) in Chapter 2 of my textbook <a href="https://primo.aalto.fi/discovery/openurl?institution=358AALTO_INST&vid=358AALTO_INST:VU1&ctx_enc=info:ofi%2FencUTF-8&rft_val_fmt=info:ofi%2Fkev:fmt:book&rft.pub=Springer&ctx_tim=2023-08-06T18:10:37EEST&rft_id=info:doi%2F10.1007%2F978-981-16-8193-6&rfr_id=info:sid%2Fpure.atira.dk:pure&ctx_ver=Z39.88-2004&rft.isbn=978-981-16-8192-9&rft.btitle=Machine%20Learning&rft.genre=book&rft.aufirst=Alex&url_ctx_fmt=info:ofi%2Ffmt:kev:mtx:ctx&rft.aulast=Jung&url_ver=Z39.88-2004&rft.auinit=A&rft.date=2022" target="_blank">here</a>. I have also prepared some lectures on these design choices which can be found [here](https://youtube.com/playlist?list=PLrbn2dGrLJK9zB7pdEd8QOtmC9-eoqoch) .

# Working on the Thesis 

The main thesis work typically consists of (several iterations of) data gathering, model selection, training and diagnosis. 
Each of these steps requires different skills and programming libraries, e.g., Python packages [`pandas`](https://pandas.pydata.org/) 
for data gathering and processing and  [`scikit-learn`](https://scikit-learn.org/stable/) for ML model selection, training and diagnosis. 
At times, you might want to reflect on your design choices and diagnosis by trying to answer the peer grading questions used 
for the student project in [CS-C3240 Machine Learning](material/CS_C3240_PeerReview.pdf) and [CS-E4740 Federated Learning](material/CS_E4740_PeerReview.pdf).

Beside the actual design and implementation of ML methods and numerical experiments, another main component of the thesis 
work is the actual writing of the thesis manuscript. To get started on the writing, you might use a template for the project reports 
used in some of my ML courses [CS-C3240 Machine Learning](material/CS_C3240_ProjectReport.pdf) and [CS-E4740 Federated Learning](https://github.com/alexjungaalto/FederatedLearning/blob/main/material/FederatedLearningPaper.pdf). However, these templates are meant as a support wheel 
and not as an application form that has to be filled out. In particular, you are very welcome to use a different outline.  

Some specific aspects that you might useful when preparing the final manuscript and that I also use as guidance
during the evaluation of your thesis: 

- As your thesis is most likely about applied ML, it is important that you precisely define/formulate the ML 
problem at hand. This formulation requires to make crystal clear to the reader what data points are (e.g., cows, clouds, measurements, specific periods of time, atoms or partial differential equations), 
which characteristics are used as their features and what is the ultimate quantity of interest (the label). You can 
read more about the formulation of ML problems in Chapter 2 of [my textbook](https://primo.aalto.fi/discovery/openurl?institution=358AALTO_INST&vid=358AALTO_INST:VU1&ctx_enc=info:ofi%2FencUTF-8&rft_val_fmt=info:ofi%2Fkev:fmt:book&rft.pub=Springer&ctx_tim=2023-08-06T18:10:37EEST&rft_id=info:doi%2F10.1007%2F978-981-16-8193-6&rfr_id=info:sid%2Fpure.atira.dk:pure&ctx_ver=Z39.88-2004&rft.isbn=978-981-16-8192-9&rft.btitle=Machine%20Learning&rft.genre=book&rft.aufirst=Alex&url_ctx_fmt=info:ofi%2Ffmt:kev:mtx:ctx&rft.aulast=Jung&url_ver=Z39.88-2004&rft.auinit=A&rft.date=2022).   

- For each ML model or method that you apply to your ML problem, you must clearly state and discuss the obtained average loss on 
training, validation (and test-) set. Comparing these average loss values is important to diagnose the ML method (see Sect. 6.6. of my textbook). 

- A key challenge in applied ML is to know when to stop iterating the model training/validation/adjustment cycle. For a master 
thesis project there is a natural stopping criterion, i.e., the deadline by which you want to submit your thesis. However, it 
might be very helpful to have a benchmark or baseline against which you can compare the obtained validation or test-set errors. 
If your ML method achieves a test-set error close the baseline level then there is little point to invest significant additional 
time into exploring other ML methods. 

- Depending on your thesis topic it might be challenging to determine a useful baseline for the achievable performance of ML methods. 
One source for such a baseline could be the expected loss (risk) of an optimal estimator under a probabilistic model (such as the "i.i.d." assumption) 
for the data points. Another source for a baseline might be any literature that has reported the average loss achieved 
by state-of-the art ML methods. This also includes unorthodox media such as online communities like [Kaggle](https://www.kaggle.com/). 

- Do not worry if you are not able to achieve a specific baseline. Instead of achieving specific performance metrics, it is much more 
important that your thesis provides a careful analysis of the obtained results. Loosely speaking: I prefer a detailed analysis of a 
(seemingly) poor performance of a ML method over a poor (or missing) analysis of a ML method with impressive performance 
in numerical experiments.  

- Try to do a first draft of the manuscript (or key parts) quick and dirty. There will be most likely several follow-up 
iterations during which you can fill in the gaps and polish the text. 

- It might be a good idea to write the thesis in a non-linear fashion. Indeed, it might be more efficient to start 
from the final Chapter (e.g., "Discussion" or "Conclusion") and then work backwards all the way to the Abstract and Introduction. 

- Try to make good use of references using `\ref{}` and `\eqref{}` LaTex commands to connect different 
parts of the thesis. In general, I like to see a strong connectivity between different parts of the thesis 
using these commands. 

- It might be a good idea to explain the outline of the thesis (its Sections and their relations) in a paragraph of the Introduction. 

- I like to see each Chapter/Section having some introductory paragraphs that briefly introduces its (sub-)sections 
and explains their relations. Moreover, these chapter introductions are also a great opportunity to bind the 
different chapters together. For example, the introduction to a Chapter 3 "Methods and Materials" could explain 
how it builds on a Chapter 2 "Basic ML Concepts". 

- You might find it useful to draw a dependency graph of your thesis with nodes being individual 
Sections (or even paragraphs) and edges obtained from references. For example node "Chapter 1" is 
connected to "Chapter 2" if there is a reference from Chapter 1 to Chapter 2 or vice-versa (the dependency graph can be 
directed or undirected). You can find a simple Python program that generates such a dependency graph from a 
LaTex ("tex") file [here](material/creategraphtex.py). 

- If your thesis presents a new ML method, it should be summarized as an algorithm pseudocode ([click me](https://www.overleaf.com/learn/latex/Algorithms)). 
An algorithm has a well-defined input (data, hyper-parameters) and output (e.g., model parameters). 

- Do not forget to label the axes of every plot. 

- Put some effort into crafting succinct and informative figure captions (some advice can be found 
[here](https://www.scu.edu/media/offices/provost/writing-center/resources/Tips-Figure-Captions.pdf)). 

- Each numbered equation, table or figure must be referred to at least once in the text. You might find this [package](https://ctan.org/pkg/refcheck?lang=de) useful.

- Ask your friends, family or colleagues to give you feedback. Our group meetings are also a good place to obtain feedback. 



# The Finish Line  

When you have completed the writing of the thesis (draft), I will ask you to prepare a self-assessment of your thesis. 
This self-assessment amounts to filling out the evaluation form [here](material/Statement_template_CCIS.docx). 
I will use a similar form to evaluate your thesis. Your self-assessment should take into account the typical grade characterizations 
<a href="material/GradeCharact.pdf" target="_blank">here</a> 
and include sufficient justifications. These justifications should be as specific as possible and include references to the 
relevant locations of your thesis (e.g., "as discussed in Section 1.1. the main research question of the thesis is ..."). 

Besides the (self-)evaluation of your thesis, finalizing your thesis typically requires to prepare a thesis presentation. 
Students can choose between different formats of this presentation. These formats include a regular in-person 
presentation during a group meeting or via a pre-recorded video (see some examples in this [YouTube Playlist](https://youtube.com/playlist?list=PLrbn2dGrLJK8xt7j0tvaL0uMCdrtQ7JY2)). 

# Feedback Please ! 

I am very happy to hear (read) your comments, suggestions or disagreement on my opinions above. 
You can contact me by email ("first (dot) last ..."), on Linkedin (https://www.linkedin.com/in/aljung/) or Twitter (@alexjungaalto). 
If you prefer, you can also use the GitHub issues, pull-requests). 





