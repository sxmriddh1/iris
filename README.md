# iris
***scout-and-defend tool that detects LLM software dependency hallucinations and flags them + vs code extension that checks dependencies against official registries as you code***

## problem domain(s):
software supply chain security, LLM security, AI security, application security, DevSecOps, operational security

## problem statement:
large language models (LLMs) are, in today's day and age, tools widely adopted by developers and professionals in software supply chains to assist in the generation and maintenance of clean, reliable code that aims to match industry standards while staying robust and catering to user requirements. 

the growing dependence on these very LLMs pose a threat - LLMs are found to hallucinate software dependency names such as Python and JavaScript packages, that look plausible but don't actually exist. a [USENIX Security 2025](https://www.usenix.org/conference/usenixsecurity25/presentation/spracklen) study found 205,474 unique hallucinated package names across 16 models.

a threat actor may prompt several LLMs to detect what dependency names, in frequency and unison, are being hallucinated and simply register those exact names on public registries like PyPI or npm, cleverly wrapping said harmless and non-existent packages with malware. 

a developer or AI assistant provided with LLM-generated code that contains hallucinated package names may install the listed dependencies without suspicion or review, and the errorless installation of the *malware* may now act as a phantom on the developer’s machine or command line, silently stealing secrets, API keys, hardcoded credentials, pivoting into pipelines or disrupting operations (worst case).


 
## solution:
 
## frameworks:

frameworks are bibles in cybersecurity\
**iris can be mapped with [mitre atlas](https://atlas.mitre.org/), [owasp top 10 LLM](https://genai.owasp.org/llm-top-10/), [mitre att&ck](https://attack.mitre.org/), [NIST cybersecurity frameworks](https://www.nist.gov/cyberframework)**\


1)  **[MITRE ATLAS (Adversarial Threat Landscape for AI Systems)](https://atlas.mitre.org):**\
   an industry framework for tactics and techniques used by attackers against AI systems, ATLAS recognises [publishing hallucinated entities (ID: AML.T0060)](https://atlas.mitre.org/techniques/AML.T0060) as one of its prominent techniques under the [resource development (ID: AML.TA0003)](https://atlas.mitre.org/tactics/AML.TA0003) objective.

&emsp;&emsp;**<ins>tactics:</ins>**\
   &emsp;&emsp;&emsp;a) [Resource Development (AML.TA0003)](https://atlas.mitre.org/tactics/AML.TA0003): attacker stages the malicious package\
   &emsp;&emsp;&emsp;b) [Discovery (AML.TA0008)](https://atlas.mitre.org/tactics/AML.TA0008): attacker finds recurring hallucinations

   &emsp;&emsp;**<ins>techniques:</ins>**\
   &emsp;&emsp;&emsp;a) [Publishing Hallucinated Entities (ID: AML.T0060)](https://atlas.mitre.org/techniques/AML.T0060): attacker registers the hallucinated name\
   &emsp;&emsp;&emsp;b) [Discover LLM Hallucinations (AML.T0062)](https://atlas.mitre.org/techniques/AML.T0062): attacker finds which names models invent\
   &emsp;&emsp;&emsp;c) [AI Model Inference API Access (AML.T0040)](https://atlas.mitre.org/techniques/AML.T0040): attacker queries the model at scale

&emsp;&emsp;**<ins>case studies:</ins>**\
&emsp;&emsp;&emsp;[ChatGPT Package Hallucination (AML.CS0022)](https://atlas.mitre.org/studies/AML.CS0022): Researchers prompted ChatGPT for package suggestions and identified the non-existent ones. They then uploaded an empty package to PyPI to track downloads.

2) **[OWASP Top 10 for LLM Applications 2025](https://genai.owasp.org/llm-top-10/):**\
   open-source, community-voted list of the top 10 most critical security risks in Large Language Models (LLMs) and related applications.

   &emsp;&emsp;a) Supply Chain [(LLM03)](https://genai.owasp.org/llmrisk/llm032025-supply-chain/): the direct, most pressing security risk linked to iris.\
   &emsp;&emsp;b) Misinformation [(LLM09)](https://genai.owasp.org/llmrisk/llm092025-misinformation/): a false but confidently suggested dependency may set as the origin of misinformation.\
   &emsp;&emsp;c) Improper Output Handling [(LLM05)](https://genai.owasp.org/llmrisk/llm052025-improper-output-handling/): validate model output before it runs

3) **[MITRE ATT&CK (Adversarial Tactics, Techniques, and Common Knowledge)](https://attack.mitre.org/):**\
knowledge base of adversary tactics and techniques based on real-world observations. ATT&CK does not model hallucination itself; it covers what happens after a malicious package reaches the developer.

&emsp;&emsp;**<ins>tactics:</ins>**\
   &emsp;&emsp;&emsp;a) [Initial Access (TA0001)](https://attack.mitre.org/tactics/TA0001/): how the malicious package gets in\
   &emsp;&emsp;&emsp;b) [Execution (TA0002)](https://attack.mitre.org/tactics/TA0002/): what runs after install

&emsp;&emsp;**<ins>techniques:</ins>**\
   &emsp;&emsp;&emsp;a) [Supply Chain Compromise (T1195)](https://attack.mitre.org/techniques/T1195/): tampering before delivery\
   &emsp;&emsp;&emsp;b) [Compromise Software Dependencies and Development Tools (T1195.001)](https://attack.mitre.org/techniques/T1195/001/): malicious dependency or dev tool\
   &emsp;&emsp;&emsp;c) [Command and Scripting Interpreter (T1059)](https://attack.mitre.org/techniques/T1059/): install hooks running shell or script code

&emsp;&emsp;**<ins>case studies:</ins>**\
&emsp;&emsp;ATT&CK has no case studies; it lists campaigns and procedure examples instead. One example on the [T1195.001](https://attack.mitre.org/techniques/T1195/001/) page is [TeamPCP](https://attack.mitre.org/groups/G1056):
**coordinated supply chain attacks on the npm, VS Code, Docker and PyPI ecosystems.**

&emsp;&emsp;**<ins>mitigations and detection:</ins>** (listed on the [T1195.001](https://attack.mitre.org/techniques/T1195/001/) page):\
   &emsp;&emsp;&emsp;a) [Application Developer Guidance (M1013)](https://attack.mitre.org/mitigations/M1013): lock dependencies to specific versions\
   &emsp;&emsp;&emsp;b) [Limit Software Installation (M1033)](https://attack.mitre.org/mitigations/M1033): pull from internal repositories of verified, approved packages\
   &emsp;&emsp;&emsp;c) [DET0009 detection strategy](https://attack.mitre.org/detectionstrategies/DET0009): dependency manager activity, then install, first run and outbound traffic

## visit:




## phase wise flow:
 

## architecture:

 
 
## tech stack:
 

  
## abstract:
 

## limitations:

## research papers:

1) **[We Have a Package for You! A Comprehensive Analysis of Package Hallucinations by Code Generating LLMs](https://www.usenix.org/conference/usenixsecurity25/presentation/spracklen)**\
   ~ *Spracklen, Wijewickrama, Sakib, Maiti, Viswanath, Jadliwala*, USENIX Security 2025

   16 models, 576,000 code samples and 205,474 unique hallucinated package names, plus tested mitigations. the core evidence behind iris.

2) **[Can you trust ChatGPT's package recommendations?](https://gwern.net/doc/www/vulcan.io/36af62ddc68a108a558a5afbee2a53774fc9b09d.html)**\
   ~ *Lanyado, Keizman, Divinsky* (Vulcan Cyber), 2023

   the original demonstration of "AI package hallucination": 227 Python questions put to ChatGPT, with a proof of concept built around an unpublished npm package.

3) **[Slopsquatting meets dependency confusion](https://nesbitt.io/2025/12/10/slopsquatting-meets-dependency-confusion)**\
   ~ *Nesbitt*, 2025

   records how the name "slopsquatting" came about, suggested by Seth Larson (PSF) and popularized by Nesbitt, and links the attack to dependency confusion.

4) **[Typosquatting and Combosquatting Attacks on the Python Ecosystem](https://iris.unitn.it/handle/11572/282646)**\
   ~ *Vu, Pashchenko, Massacci, Plate, Sabetta*, IEEE EuroS&P Workshops 2020

   studies typosquatting and combosquatting on PyPI and proposes a way to identify such names automatically.

5) **[Dependency Confusion: How I Hacked Into Apple, Microsoft and Dozens of Other Companies](https://medium.com/@alex.birsan/dependency-confusion-4a5d60fec610)**\
   ~ *Birsan*, February 2021

   the write-up that introduced dependency confusion, where public packages named like internal ones get pulled in by package managers.

6) **[Backstabber's Knife Collection: A Review of Open Source Software Supply Chain Attacks](https://arxiv.org/abs/2005.09535)**\
   ~ *Ohm, Plate, Sykosch, Meier*, DIMVA 2020

   a review built on a dataset of real malicious packages, a possible source of malicious-class labels for iris's evaluation.

7) **[SoK: Taxonomy of Attacks on Open-Source Software Supply Chains](https://arxiv.org/abs/2204.04008)**\
   ~ *Ladisa, Plate, Martinez, Barais*, IEEE Symposium on Security and Privacy 2023

   a taxonomy of attacks on open-source supply chains, useful for positioning iris among known attack vectors.

8) **[Secure Software Development Framework (SSDF) Version 1.1: Recommendations for Mitigating the Risk of Software Vulnerabilities (NIST SP 800-218)](https://csrc.nist.gov/pubs/sp/800/218/final)**\
   ~ *Souppaya, Scarfone, Dodson*, NIST, February 2022

   a core set of high-level secure development practices. iris is a complementary dependency-verification practice, not a replacement.

9) **[SLSA (Supply-chain Levels for Software Artifacts)](https://slsa.dev/)**\
   ~ *SLSA community*, ongoing

   a framework for provenance and build integrity, a future-scope complement to iris's existence and risk checks.

## license:
 
MIT — see `LICENSE`.
 
## contributors and project timeline:
created by: samriddhi guha (samriddhiguha777@gmail.com) 

timeline: october 28, 2026 - present

 
