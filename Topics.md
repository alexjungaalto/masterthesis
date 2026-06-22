# Available Master's Thesis Topics

Open topics for a master's thesis supervised by [Alex Jung](https://machinelearningforall.github.io/about/), Associate Professor for Machine Learning at Aalto University.

To discuss a topic or propose your own, get in touch — see the contact links in the [thesis guide](index.md#feedback-and-questions).

## Distributed ML systems and AI policy

### A National Inference Grid: Could a Country Run Its Own AI Beyond Big Tech?

**Difficulty:** Advanced · **Data source:** Public compute and telecom data

Today, powerful AI language models usually run inside the data centres of a few large technology companies. This topic asks a different question: could a country instead run such a model itself, by pooling together many ordinary computers spread across the country? And if so, who should own and run that shared system? A useful comparison is the mobile phone network. It is essential, everyday infrastructure that a whole country depends on, yet it is not owned by the state: it is built and run by a small number of private companies that are licensed and regulated to serve the public. Could a national AI capability be organised the same way? The thesis weighs this telecom model against other options too, from public roads that everyone can use to community-run projects with no central owner. The student studies whether the idea could work well enough in practice, whether it would be cheaper than renting from big cloud providers, and what ownership and rules would make it trustworthy and independent. The work stays focused on one main angle so it remains a single thesis. Suitable for a student interested in AI, computing infrastructure, and technology policy.

**References**

1. A. Borzunov et al., "Distributed Inference and Fine-tuning of Large Language Models Over the Internet," in *Proc. NeurIPS*, 2023. [Online]. Available: <https://arxiv.org/abs/2312.08361>
2. European Commission, "AI Factories," *Shaping Europe's Digital Future*. [Online]. Available: <https://digital-strategy.ec.europa.eu/en/policies/ai-factories>

[Ask about this topic](mailto:alex.jung@aalto.fi?subject=Thesis%20topic:%20A%20National%20Inference%20Grid:%20Could%20a%20Country%20Run%20Its%20Own%20AI%20Beyond%20Big%20Tech?)

## Political data science

### Political Influence on Childcare Provision in Rural Austria

**Difficulty:** Intermediate · **Data source:** data.gv.at

Analyse whether and how local political leadership correlates with the availability of publicly funded childcare in rural Austrian municipalities, using open government data. Methods: data aggregation, correlation and regression analysis, before/after-election comparisons, and optionally causal inference. Tools: Python, pandas, geopandas. Suits students interested in political data science and regional development with a solid Python and statistics background.

[Ask about this topic](mailto:alex.jung@aalto.fi?subject=Thesis%20topic:%20Political%20Influence%20on%20Childcare%20Provision%20in%20Rural%20Austria)

## Machine learning theory and model auditing

### Compressed Sensing of LLMs: Query-Efficient Recovery of a Black-Box Next-Token Function

**Difficulty:** Advanced · **Data source:** Open-weight LLMs (Pythia, Qwen, Llama)

An LLM can be viewed as a single unknown function: give it a context, it returns scores for the next token. This topic poses a compressed-sensing question about that function: how much of it can be reconstructed from a limited number of black-box queries, and what is the smallest number of queries needed? Classical compressed sensing recovers a high-dimensional signal from few measurements when the signal is structured; here the structure comes from how transformers are built (low-dimensional hidden states, smoothness, limited model complexity) and each query is one measurement. The thesis develops the theory (when do queries pin the model down, and a matching lower bound on how many are required) and tests it on open-weight models such as Pythia, Qwen and Llama, including under realistic API limits (top-k outputs, sampling noise, rate limits). The pay-off is a precise account of how auditable a deployed model is from the outside, and which deployment choices provably limit what an outsider can recover - a contribution to model auditing and trustworthy AI. Strong background in linear algebra, high-dimensional probability and statistical learning theory (or compressed sensing) recommended, plus comfort running open-weight LLMs in PyTorch.

[Read the full proposal](topics/compressed-sensing-llms/proposal.pdf)

**References**

1. D. L. Donoho, "Compressed sensing," *IEEE Trans. Inf. Theory*, vol. 52, no. 4, pp. 1289-1306, 2006.
2. F. Tramèr, F. Zhang, A. Juels, M. K. Reiter, and T. Ristenpart, "Stealing machine learning models via prediction APIs," in *Proc. 25th USENIX Security Symp.*, 2016, pp. 601-618.
3. N. Carlini et al., "Stealing part of a production language model," in *Proc. ICML*, 2024. [Online]. Available: <https://arxiv.org/abs/2403.06634>

[Ask about this topic](mailto:alex.jung@aalto.fi?subject=Thesis%20topic:%20Compressed%20Sensing%20of%20LLMs:%20Query-Efficient%20Recovery%20of%20a%20Black-Box%20Next-Token%20Function)
