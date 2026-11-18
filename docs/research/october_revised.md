Source: https://docs.google.com/document/d/101lwA072svU0OiiWLtVKT04yw_suaWw0/edit
Retrieved: 2026-11-18

Research overview
Validation criteria for algorithms
Psychological validation side of giving tips
General validation considerations
It is difficult to validate the model without testing it with users.
Possible approaches include:
Synthetic data representing periods before and after tips are provided
A model that incorporates tips and applies them to a simulated household with a certain probability, reflecting the fact that users may not follow every tip.
Both approaches have limitations: they would require us to create a separate model to validate our model, which would itself need to be validated. This would therefore shift, rather than resolve, the validation challenge.
If we had access to data from before and after tips were provided, or chose to use synthetic data (which would require substantial justification), and conducted small controlled trials, the following methods could be considered:
One possible method, if access to an individual household were available, would be a Micro-Randomized Trial (https://metricgate.com/docs/micro-randomized-trial/). This approach examines an individual's decision points. The method is described as follows: “This enables estimation of proximal causal effects of just-in-time adaptive interventions (JITAIs) delivered via mobile devices, providing the empirical foundation for building effective digital health tools.”https://metricgate.com/docs/micro-randomized-trial/
This would help assess whether the tips are appropriate and whether users follow them.
Validating whether the tips lead to actual financial savings would be considerably more difficult and would require a much larger trial.
This represents a significant limitation of the project.
Validating the models
These issues need to be addressed before the models can be properly validated.
Event detection: The main limitation is the lack of datasets in which events are explicitly labelled with their occurrence time. Without these reference labels, it is not currently possible to validate event detection.
Event detection
Evaluation and validation metrics
Common evaluation metrics include F1-score, precision, recall, and AUC-ROC. However, the available data does not include the required labels:
Option 1: https://www.kaggle.com/competitions/energy-anomaly-detection 
The dataset includes anomaly labels (1 for abnormal and 0 for normal observations). However, it covers electricity data only, at an hourly resolution.
Option 2: Introduce artificial events into the selected datasets and label them. This would evaluate the model's ability to detect artificial anomalies, but would not necessarily demonstrate performance on real-world events.
This approach has been used in previous projects. For example, the following paper evaluates different event-detection algorithms using synthetic abnormalities: https://vldb.org/pvldb/vol15/p1779-wenig.pdfhttps://vldb.org/pvldb/vol15/p1779-wenig.pdf
Research has also examined how to make synthetic anomalies more representative of real-world cases. The following paper proposes a method based on four commonly occurring anomaly types in real energy data and develops mathematical models to reproduce them: https://dl.acm.org/doi/10.1145/3538637.3539760. A similar approach could help avoid relying on random peaks that may not reflect relevant real-world situations. The associated implementation is available here: https://github.com/KIT-IAI/GeneratingSyntheticEnergyPowerAnomalieshttps://dl.acm.org/doi/10.1145/3538637.3539760https://github.com/KIT-IAI/GeneratingSyntheticEnergyPowerAnomalies
https://peerj.com/articles/cs-1721/Another approach uses transformers; a GitHub implementation is available: https://peerj.com/articles/cs-1721/
Success criteria
If these evaluation metrics are used, the following thresholds could serve as initial reference points:
Precision and recall >80% → success
F1-score > 0.8
AUC: Monitor the frequency of false alerts, as excessive anomaly notifications may be disruptive to users.
We also need to distinguish genuine anomalies from natural consumption peaks, for example those caused by visitors or colder weather, and evaluate the model accordingly.
HOUSEHOLD PROFILE
For the household profile, some NILM validation may be possible using UK-DALE or other datasets that include appliance-level data. However, other forms of validation are limited by the lack of suitable data.
Specific numerical success criteria may also need to be defined.
The contents of the new household profile are not yet clear. For now, the following assumptions are used:
Data collection: The code already includes basic correctness and data-quality checks. These may be sufficient, although this should be confirmed.
Expected energy and gas usage: This depends on how these values are calculated.
Psychological aspect of tips
This topic is referenced in the project plan and is relevant to the design of the tip engine:
https://sci-hub.in/https://doi.org/10.1007/s12053-008-9009-7
The source is relatively abstract:
A short article discussing the paper by Shahzeen Z. Attari, Michael L. DeKay, Cliff I. Davidson, and Wandi Bruine de Bruin, “Public perceptions of energy consumption and savings,” Proceedings of the National Academy of Sciences 107, no. 37 (2010): 16054–16059.
https://environment-review.yale.edu/think-youre-saving-energy-you-might-want-think-again-0
“In short, people have a far better understanding of energy use when it comes to small things like a light bulb than, say, a dishwasher.”. 
This suggests that the system could focus on communicating the energy consumption of larger appliances.
This UK study may also be relevant:
https://ora.ox.ac.uk/objects/uuid:bfa5f642-f75c-4ed0-91f7-e363243a7a09/files/m3bba262f85994e5cb155a0ea525a4545
One possible takeaway is that energy advice may have a stronger impact when paired with direct feedback tools.
Other relevant literature:
https://www.researchgate.net/profile/Helmut-Jungermann/publication/3804909_Advice_Giving_and_Taking/links/564894b308ae451880ae85be/Advice-Giving-and-Taking.pdf
https://www.apa.org/pubs/journals/releases/bul-a0039650.pdf
https://pmc.ncbi.nlm.nih.gov/articles/PMC9989172/
Validating the psychological aspects would require a controlled trial and participant surveys. This may not be feasible or necessary within the project. The literature should therefore inform the design of the tip engine, as psychological validation without participant involvement would not be possible.
The research leads to two main questions:
How can we evaluate the model?
This includes establishing how we can validate the following aspects, as well as defining the success criteria for each:
Household profile:
Event detection: Does our model correctly identify unusual energy consumption?
Tip recommendation: Does our model correctly predict what needs to be done based on energy consumption and provide appropriate tips?
Savings estimation: Are the estimated euro savings calculated correctly, and are the assumptions realistic? 
Are the tips useful to the target group?
This concerns not necessarily whether the tips reduce energy consumption (which would require further validation), but whether they are suitable for and likely to be used by the target group.
The considerations raised by the examiner regarding literacy, poverty, and lower education levels within the target group should also be taken into account.
A practical approach would be to identify an existing set of tips, or guidelines for phrasing tips, that have already been validated with similar target groups.
More specifically, we should focus on three aspects:
Understandability: Can people with limited literacy or digital skills easily understand the tips?
Feasibility: Can people realistically follow the tips, considering their income, housing situation, and available resources?
Motivation: Would people actually want to follow the tips?
Existing research could be used to support decisions about the design and wording of the tips.
Reading list
@article{kramer2016financial,
  title={Financial literacy, confidence and financial advice seeking},
  author={Kramer, Marc M},
  journal={Journal of economic behavior \& organization},
  volume={131},
  pages={198--217},
  year={2016},
  publisher={Elsevier}
}
@article{simcock2025cure,
  title={A cure-all for energy poverty? Thinking critically about energy advice},
  author={Simcock, Neil and Bouzarovski, Stefan},
  journal={Critical social policy},
  volume={45},
  number={1},
  pages={49--71},
  year={2025},
  publisher={SAGE Publications, Sage UK: London, England}
}
@techreport{ambrose2019reaching,
  title={Reaching the'Hardest to Reach'with energy advice},
  author={Ambrose, Aimee and Baker, William and Batty, Elaine and Hawkins, Anna},
  year={2019},
  institution={Sheffield Hallam University}
}
@article{laskari2016design,
  title={The design of an energy and water advice programme for low-income households},
  author={Laskari, Marina and Karatasou, Stavroula and Santamouris, Mat},
  journal={Energy and Buildings},
  volume={110},
  pages={426--434},
  year={2016},
  publisher={Elsevier}
}
@article{dellavalle2019people,
  title={People’s decisions matter: understanding and addressing energy poverty with behavioral economics},
  author={DellaValle, Nives},
  journal={Energy and Buildings},
  volume={204},
  pages={109515},
  year={2019},
  publisher={Elsevier}
}
A small user test or questionnaire with members of the target group could be used to assess whether the tips are understandable, feasible, and appealing. However, this is considered a lower project priority, as it would require additional time and is not currently among the main project priorities.
17/11
Long periods anomalies 
Label consistent household….
https://arxiv.org/pdf/1003.5956

Unbiased Offline Evaluation of Contextual-bandit-based
News Article Recommendation Algorithms

The contextual-bandit model is used to identify the most suitable option for a user based on their context.

The paper discusses methods for evaluating these models without bias.
https://arxiv.org/pdf/1912.13088v2

Off-Policy Estimation of Long-Term Average
Outcomes with Applications to Mobile Health

Another method for validating and quantifying the performance of a tip predictor. However, it requires user data.
https://eta-publications.lbl.gov/publications/simulation-driven-rating-smart

Simulation-Driven Rating of Smart Thermostats

The authors developed a simulation-driven framework for evaluating smart thermostats, which may be relevant.
