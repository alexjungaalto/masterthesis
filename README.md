# Doing a Master Thesis on Applied Machine Learning

Applied machine learning (ML) transforms data into meaningful insights across 
domains—from healthcare and finance to climate science and beyond. If you're 
interested in exploring a research question or application using ML, consider 
having [me](https://machinelearningforall.github.io/about/) as your thesis supervisor.

You can find a list of master’s theses currently supervised by me [here](material/MasterThesisSupervisedCurrent.pdf).

You can find potential topics for a master thesis [here](Topics.md)

## What can you expect from me as your supervisor?

As your supervisor, you can expect me to:

- Help you clearly define your ML problem.
- Advise you on suitable ML methods, tools, and resources.
- Guide you through thesis writing and evaluation.

## Getting Started

To start your thesis:

1. **Formulate your ML problem** clearly by identifying data points, their features and labels ([watch this video](https://youtu.be/2q5jpvD-638)).
2. **Choose suitable ML models**  that you are comfortable implementing (e.g., linear regression, random forests or artificial neural networks).
3. **Identify data sources and evaluation criteria** (e.g., test accuracy, computational efficiency).

You can find detailed guidance in [Chapter 2 of my textbook](https://primo.aalto.fi/discovery/openurl?institution=358AALTO_INST&vid=358AALTO_INST:VU1&ctx_enc=info:ofi%2FencUTF-8&rft_val_fmt=info:ofi%2Fkev:fmt:book&rft.pub=Springer&rft_id=info:doi%2F10.1007%2F978-981-16-8193-6).

Additionally, I've prepared [lecture videos on these topics](https://youtube.com/playlist?list=PLrbn2dGrLJK9zB7pdEd8QOtmC9-eoqoch).

## Practical Workflow

A master thesis in machine learning typically involves:

- **Data Collection and Preprocessing** using, e.g., [pandas](https://pandas.pydata.org/).
- **Model Training and Validation** using, e.g., [scikit-learn](https://scikit-learn.org/).
- **Model Diagnosis** using numerical experiments (benchmarks, sensitivity analysis) and (when appropriate) 
mathematical analysis (generalisation bounds, error analysis, comparison to Bayes’ risk).

For your thesis work, you should primarily rely on **high-quality scientific references**, 
such as peer-reviewed journal articles, reputable conference papers, and established 
textbooks. Suitable sources can be found in major academic databases, including:

- **Aalto University Library** (access to licensed databases and books):  
 https://primo.aalto.fi/discovery/search?vid=358AALTO_INST:VU1&lang=en
- **IEEE Xplore**:  
  https://ieeexplore.ieee.org  
- **ACM Digital Library**:  
  https://dl.acm.org  
- **Scopus**:  
  https://www.scopus.com  
- **Web of Science**:  
  https://www.webofscience.com  

To assess the standing and quality of journals and conferences, you may consult the **JUFO ranking system**:  
https://jfp.csc.fi/jufoportal

If you are uncertain about the quality or relevance of a reference, you are encouraged to 
ask me for guidance on appropriate and credible sources.


### References 

- A. Jung et.al, "The Aalto Dictionary of Machine Learning," Aalto University. [Click here](https://aaltodictionaryofml.github.io/) for the Github work. 
- S. Shalev-Shwartz and S. Ben-David, Understanding Machine Learning: From Theory to Algorithms. Cambridge, U.K.: Cambridge University Press, 2014.
- [Peer-Review for Machine Learning Course Project](material/CS_C3240_PeerReview.pdf)
- [Peer-Review for Federated Learning Course Project](material/CS_E4740_PeerReview.pdf)

## Thesis Manuscript Preparation

When preparing your thesis, ensure:

- Use the terms defined in the *([Aalto Dictionary of ML](https://aaltodictionaryofml.github.io/))*. You are also encouraged to use the 
source code of the dictionary (e.g., for creating TikZ figures). 
- The ML problem is precisely defined: you make crystal clear what the data points are, and how their features and labels are defined.
- You explicitly state the loss function used to measure prediction quality. You might using different loss functions for the training 
  of a model and for its validation or testing.  
- Numerical results are clearly presented and thoroughly discussed to answer the research questions.
- Appropriate baselines or benchmarks are used (e.g., [Kaggle competitions](https://kaggle.com)).
- Chapters and sections are clearly structured, with introductory paragraphs explaining content and connections.
- Equations, figures, and tables are consistently referenced using LaTeX commands (`\ref{}`, `\eqref{}`). **Only number mathematical displays that are referenced in the text.; unreferenced equations should remain unnumbered.**
- New methods are presented as pseudocode ([see examples](https://www.overleaf.com/learn/latex/Algorithms)).
- Figures are clear, labeled, and have informative captions ([guidelines](https://www.scu.edu/media/offices/provost/writing-center/resources/Tips-Figure-Captions.pdf)).
- References are formatted according to the [IEEE guidelines](https://journals.ieeeauthorcenter.ieee.org/wp-content/uploads/sites/7/IEEE_Reference_Guide.pdf).

For guidance on creating effective and visually appealing figures, consider consulting Edward Tufte's classic 
book ["The Visual Display of Quantitative Information"](https://www.edwardtufte.com/tufte/books_vdqi).

I also strongly encourage you to make use of our open-source Aalto Dictionary of Machine Learning 
which provides tex code for core ML terms and figures. You can find the dictionary here: 
[click me](https://github.com/AaltoDictionaryofML/AaltoDictionaryofML.github.io). 


### References

- [Ten Simple Rules for Mathematical Writing](https://www.mit.edu/~dimitrib/Ten_Rules.html) by D. Bertsekas. 

- E. Tufte, "The Visual Display of Quantitative Information", 2nd Edition 2001.

- A. Jung et.al, "The Aalto Dictionary of Machine Learning," Aalto University. [Click here](https://aaltodictionaryofml.github.io/) for the Github work. 

## Typesetting Mathematical Texts

If your thesis includes equations or derivations, follow these typesetting conventions:

### Display vs Inline Math

- Use **inline math** (`$...$`) for short expressions:  
  `The loss is defined as $L(\theta)$.`
- Use **display math** (`\[ ... \]` or `equation` environment) for standalone equations that are central or referenced.

### Punctuation with Displayed Equations

- **Punctuate displayed math as part of the sentence**:
  ```latex
  \[
  L(\theta) = \frac{1}{n} \sum_{i=1}^n \ell(f(x_i;\theta), y_i).
  \]

### References

- Donald E. Knuth, Tracy Larrabee, and Paul M. Roberts — Mathematical Writing
A concise and insightful guide on how to write mathematics clearly and precisely.
[Available as a free PDF](https://tex.loria.fr/typographie/mathwriting.pdf)

- IEEE Style Guide: [Editing Mathematics for IEEE Style](https://journals.ieeeauthorcenter.ieee.org/wp-content/uploads/sites/7/Editing-Mathematics.pdf)

- [IEEE EDITORIAL STYLE MANUAL FOR AUTHORS](https://journals.ieeeauthorcenter.ieee.org/wp-content/uploads/sites/7/IEEE-Editorial-Style-Manual-for-Authors.pdf), 2024


## Iterative Writing Process

Expect multiple iterations on your manuscript:

- Write your first draft quickly to capture your main ideas.
- Regularly incorporate feedback from peers, group meetings, or, where appropriate, LLM-based tools.
- Consider writing non-linearly, starting from results or discussion and working backwards to the introduction.

## Final Thesis Checklist

Before submitting your thesis, verify:

- [ ] Clear problem formulation
- [ ] Methods clearly described, including pseudocode
- [ ] Clear figures with labeled axes and informative captions
- [ ] All equations, tables, and figures referenced in the text
- [ ] Citations formatted correctly
- [ ] Self-assessment form completed ([form here](material/Statement_template_CCIS.docx))

## Thesis Evaluation and Presentation

Upon completion:

- Complete a detailed self-assessment ([evaluation form](material/Statement_template_CCIS.docx)), clearly referencing sections of your thesis.
- Review the [grade characterization PDF](material/GradeCharact.pdf) for guidance on what constitutes a high-quality thesis.
- Prepare your thesis presentation (live during a group meeting or as a recorded video; see [examples here](https://youtube.com/playlist?list=PLrbn2dGrLJK8xt7j0tvaL0uMCdrtQ7JY2)).

I discuss my approach to grading master’s theses in this [YouTube video](https://youtu.be/HWHWAy9sOFk?si=-6sPplFx0Gvj0SFJ)

## Feedback and Questions

I'm always eager for your feedback or questions. Reach out via:

- **Email:** firstname.lastname@aalto.fi  
- **LinkedIn:** [linkedin.com/in/aljung/](https://www.linkedin.com/in/aljung/)  
- **YouTube:** [@alexjung111](https://www.youtube.com/@alexjung111)  
- **GitHub:** Use issues or pull requests.
