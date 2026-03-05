# Master Thesis in Applied Machine Learning

This repository contains guidance for students doing a master's thesis supervised by [Alex Jung](https://machinelearningforall.github.io/about/) at Aalto University.

- Currently supervised theses: [MasterThesisSupervisedCurrent.pdf](material/MasterThesisSupervisedCurrent.pdf)
- Available topics: [Topics.md](Topics.md)

---

## Table of Contents

1. [What to Expect from Your Supervisor](#what-to-expect-from-your-supervisor)
2. [What Is Expected from You](#what-is-expected-from-you)
3. [Getting Started](#getting-started)
4. [Typical Timeline](#typical-timeline)
5. [Recommended Development Environment](#recommended-development-environment)
6. [Responsible Use of AI](#responsible-use-of-ai)
7. [Practical Workflow](#practical-workflow)
8. [Thesis Manuscript Preparation](#thesis-manuscript-preparation)
9. [Typesetting Mathematical Texts](#typesetting-mathematical-texts)
10. [Iterative Writing Process](#iterative-writing-process)
11. [Final Thesis Checklist](#final-thesis-checklist)
12. [Thesis Presentation and Self-Evaluation](#thesis-presentation-and-self-evaluation)
13. [Thesis Evaluation, Decision, and Appeals](#thesis-evaluation-decision-and-appeals)
14. [References](#references)
15. [Feedback and Questions](#feedback-and-questions)

---

## What to Expect from Your Supervisor

As your supervisor, you can expect me to:

- Help you clearly define your ML problem.
- Advise on suitable ML methods, tools, and resources.
- Guide you through thesis writing and evaluation.
- Provide feedback on drafts and self-assessments.
- Offer the opportunity to discuss your self-assessment before submission.

## What Is Expected from You

As a thesis student, you are expected to:

- Take ownership of your research and drive progress independently.
- Come to meetings prepared with concrete questions or results.
- Communicate proactively — notify me early if you are stuck or falling behind schedule.
- Use high-quality scientific references (peer-reviewed journals, reputable conferences, established textbooks).
- Follow the writing and typesetting conventions described in this guide.

---

## Getting Started

To start your thesis:

1. **Formulate your ML problem** clearly by identifying data points, their features, and labels ([watch this video](https://youtu.be/2q5jpvD-638)).
2. **Choose suitable ML models** that you are comfortable implementing (e.g., linear regression, random forests, or neural networks).
3. **Identify data sources and evaluation criteria** (e.g., test accuracy, computational efficiency).

Detailed guidance is available in [Chapter 2 of the textbook](https://primo.aalto.fi/discovery/openurl?institution=358AALTO_INST&vid=358AALTO_INST:VU1&ctx_enc=info:ofi%2FencUTF-8&rft_val_fmt=info:ofi%2Fkev:fmt:book&rft.pub=Springer&rft_id=info:doi%2F10.1007%2F978-981-16-8193-6) and in these [lecture videos](https://youtube.com/playlist?list=PLrbn2dGrLJK9zB7pdEd8QOtmC9-eoqoch).

---

## Typical Timeline

A master's thesis typically spans 6–12 months. Below is a rough breakdown:

| Phase | Activities |
|---|---|
| **Problem Definition** | Identify research question, data sources, and evaluation criteria |
| **Literature Review** | Survey related work; identify gaps your thesis addresses |
| **Data Collection & Preprocessing** | Gather, clean, and explore your dataset |
| **Modeling** | Implement and train ML models; run baseline experiments |
| **Evaluation & Diagnosis** | Benchmarks, sensitivity analysis, error analysis |
| **Writing** | Draft chapters iteratively; incorporate feedback |
| **Self-Assessment & Presentation** | Complete evaluation form; prepare and deliver thesis presentation |

---

## Recommended Development Environment

[Visual Studio Code](https://code.visualstudio.com/) is a good choice for thesis work — it supports LaTeX (via the [LaTeX Workshop](https://marketplace.visualstudio.com/items?itemName=James-Yu.latex-workshop) extension), Python, and Jupyter notebooks in one place.

The [Claude Code extension for VS Code](https://marketplace.visualstudio.com/items?itemName=Anthropic.claude-code) integrates an AI assistant directly into your editor. You can use it to:

- Explain or refactor Python/LaTeX code in context
- Get feedback on a selected paragraph or equation
- Generate boilerplate (e.g., plotting code, pseudocode skeletons)
- Ask questions about your codebase without leaving the editor

> **Note:** Treat AI-generated content critically. Verify any code it produces, and do not use it to write substantive thesis text — your analysis and conclusions must be your own.

---

## Responsible Use of AI

Aalto University has official policies on AI use in research and studies. You are expected to follow these:

- [Responsible use of AI in the research process](https://www.aalto.fi/en/services/responsible-use-of-artificial-intelligence-in-the-research-process) — Aalto University
- [Tips for using AI for students](https://www.aalto.fi/en/services/tips-for-using-artificial-intelligence-for-students) — Aalto University

The key principles are summarised below.

### Authorship and Accountability

- AI cannot be listed as an author. You bear full responsibility for every claim, result, and conclusion in your thesis.
- Never use AI as a disclaimer — the fact that AI produced something does not excuse errors or misconduct.

### Disclosure

- **Always disclose** when and how you used AI tools. In a thesis, this belongs in a dedicated statement — not in the Methods section, which is reserved for your actual research methods.
- Record which tool, version, and settings you used so that your process is transparent (exact reproduction via online services is often impossible as they update frequently).

### Data Protection and IP

- Do not upload personal data, confidential data, or unpublished manuscripts to public AI services — this may violate GDPR.
- Be aware that AI-generated content may embed others' work without traceable references. Verify all citations independently.
- For sensitive data, use local or GDPR-compliant AI tools only.

### Permitted Uses in Thesis Work

AI tools can support your work without compromising integrity when used for:

- Proofreading language and grammar
- Brainstorming research directions or experiment designs
- Explaining concepts or summarising background literature (always verify)
- Generating boilerplate code or plotting templates (always review and test)
- Identifying counterarguments to strengthen your reasoning

### What AI Cannot Replace

- Your own critical analysis and interpretation of results
- Independent evaluation of source quality and relevance

## Practical Workflow

A master's thesis in machine learning typically involves:

- **Data Collection and Preprocessing** using, e.g., [pandas](https://pandas.pydata.org/).
- **Model Training and Validation** using, e.g., [scikit-learn](https://scikit-learn.org/).
- **Model Diagnosis** using numerical experiments (benchmarks, sensitivity analysis) and, when appropriate, mathematical analysis (generalisation bounds, error analysis, comparison to Bayes' risk).

For academic sources, use:

- **Aalto University Library**: https://primo.aalto.fi/discovery/search?vid=358AALTO_INST:VU1&lang=en
- **IEEE Xplore**: https://ieeexplore.ieee.org
- **ACM Digital Library**: https://dl.acm.org
- **Scopus**: https://www.scopus.com
- **Web of Science**: https://www.webofscience.com

To assess the quality of journals and conferences, consult the **JUFO ranking system**: https://jfp.csc.fi/jufoportal

If you are uncertain about a reference's quality, ask me.

---

## Thesis Manuscript Preparation

When preparing your thesis, ensure:

- **Terminology**: Use terms defined in the [Aalto Dictionary of ML](https://aaltodictionaryofml.github.io/). You are encouraged to reuse its LaTeX source (e.g., TikZ figures).
- **Problem formulation**: State clearly what the data points are and how their features and labels are defined.
- **Loss functions**: Explicitly state the loss function used for training and, separately, for validation or testing.
- **Numerical results**: Present and discuss results thoroughly to answer your research questions.
- **Baselines**: Use appropriate baselines or benchmarks (e.g., [Kaggle competitions](https://kaggle.com)).
- **Structure**: Begin each chapter and section with an introductory paragraph explaining its content and its connection to the rest of the thesis.
- **Equations**: Reference all numbered equations using `\eqref{}`. Only number equations that are referenced in the text; leave unreferenced equations unnumbered.
- **Algorithms**: Present new methods as pseudocode ([see examples](https://www.overleaf.com/learn/latex/Algorithms)).
- **Figures**: Ensure all figures are clear, labeled, and have informative captions ([caption guidelines](https://www.scu.edu/media/offices/provost/writing-center/resources/Tips-Figure-Captions.pdf)).
- **References**: Format according to [IEEE guidelines](https://journals.ieeeauthorcenter.ieee.org/wp-content/uploads/sites/7/IEEE_Reference_Guide.pdf).

For creating effective figures, see Edward Tufte's [The Visual Display of Quantitative Information](https://www.edwardtufte.com/tufte/books_vdqi).

---

## Typesetting Mathematical Texts

### Display vs Inline Math

- Use **inline math** (`$...$`) for short expressions within a sentence:
  `The loss is defined as $L(\theta)$.`
- Use **display math** (`\[ ... \]` or the `equation` environment) for standalone equations that are central or referenced.

### Punctuation with Displayed Equations

Punctuate displayed math as part of the surrounding sentence:

```latex
The empirical risk is defined as
\[
L(\theta) = \frac{1}{n} \sum_{i=1}^n \ell(f(x_i;\theta), y_i).
\]
```

---

## Iterative Writing Process

- Write your first draft quickly to capture main ideas — do not wait until results are final.
- Write non-linearly if helpful: start from results or discussion, then work backwards to the introduction.
- Incorporate feedback regularly from peers, group meetings, or, where appropriate, LLM-based tools.
- Expect and budget for multiple revision rounds before submission.

---

## Final Thesis Checklist

Before submitting, verify each item below. Links point to the relevant section of this guide.

- [ ] ML problem is precisely formulated: data points, features, and labels are clearly defined (see [Getting Started](#getting-started))
- [ ] Loss functions for training and evaluation are explicitly stated (see [Manuscript Preparation](#thesis-manuscript-preparation))
- [ ] Methods are clearly described, including pseudocode for new algorithms
- [ ] Baselines or benchmarks are included and discussed
- [ ] All figures have labeled axes and informative captions
- [ ] All numbered equations, tables, and figures are referenced in the text
- [ ] Citations are formatted according to IEEE guidelines
- [ ] Self-assessment form is completed ([form here](material/Statement_template_CCIS.docx))

---

## Thesis Presentation and Self-Evaluation

After completing the thesis manuscript:

- Complete the detailed self-assessment ([evaluation form](material/Statement_template_CCIS.docx)), with explicit references to sections of your thesis.
- Review the [grade characterization PDF](material/GradeCharact.pdf) to understand what constitutes a high-quality thesis.
- Optionally, request a meeting to discuss your self-assessment before submission.
- Prepare your thesis presentation — either live during a group meeting or as a recorded video ([see examples](https://youtube.com/playlist?list=PLrbn2dGrLJK8xt7j0tvaL0uMCdrtQ7JY2)).

---

## Thesis Evaluation, Decision, and Appeals

[YouTube overview](https://youtu.be/HWHWAy9sOFk?si=-6sPplFx0Gvj0SFJ)

### How the grade is decided

- Your thesis is evaluated against the **official programme and school-level criteria**.
- I prepare a written evaluation and a **grade proposal** based on these criteria.
- The **final grade is confirmed by the programme or school** following Aalto University's formal procedures.
- Study the [grade characterization document](material/GradeCharact.pdf) carefully before submission.

### Transparency and feedback

- You have the right to **see the evaluation criteria** applied to your thesis.
- You may request clarification on how your thesis was assessed and how the grade was formed.
- The **self-assessment form** is an important part of this process.

### Appealing a grading decision

- If you believe an error occurred, you have the right to **request rectification** of the grade.
- Appeals must be submitted **within 14 days** of being notified of the grade or of being given the opportunity to review the evaluation.
- See [Academic Appeals at Aalto University](https://www.aalto.fi/en/applications-instructions-and-guidelines/academic-appeals) for the formal procedure.

**Practical advice:** If unsure whether an appeal is appropriate, discuss the evaluation with your supervisor first. Many issues can be resolved without a formal appeal.

---

## References

### ML Fundamentals

- A. Jung et al., "The Aalto Dictionary of Machine Learning," Aalto University. [[GitHub]](https://aaltodictionaryofml.github.io/)
- S. Shalev-Shwartz and S. Ben-David, *Understanding Machine Learning: From Theory to Algorithms*. Cambridge University Press, 2014.
- [Peer-Review Form — Machine Learning Course Project](material/CS_C3240_PeerReview.pdf)
- [Peer-Review Form — Federated Learning Course Project](material/CS_E4740_PeerReview.pdf)

### Writing and Typesetting

- D. Bertsekas, [Ten Simple Rules for Mathematical Writing](https://www.mit.edu/~dimitrib/Ten_Rules.html)
- D. E. Knuth, T. Larrabee, and P. M. Roberts, [Mathematical Writing](https://mirror.gutenberg-asso.fr/tex.loria.fr/typographie/mathwriting.pdf)
- E. Tufte, *The Visual Display of Quantitative Information*, 2nd ed., 2001.
- [AMS Style Guide for Journals](https://www.ams.org/publications/authors/AMS-StyleGuide-online.pdf)
- [IEEE Editing Mathematics Style Guide](https://journals.ieeeauthorcenter.ieee.org/wp-content/uploads/sites/7/Editing-Mathematics.pdf)
- [IEEE Editorial Style Manual for Authors](https://journals.ieeeauthorcenter.ieee.org/wp-content/uploads/sites/7/IEEE-Editorial-Style-Manual-for-Authors.pdf), 2024

---

## Feedback and Questions

Reach out via:

- **Email:** alex.jung@aalto.fi
- **LinkedIn:** [linkedin.com/in/aljung/](https://www.linkedin.com/in/aljung/)
- **YouTube:** [@alexjung111](https://www.youtube.com/@alexjung111)
- **GitHub:** Use issues or pull requests on this repository.
