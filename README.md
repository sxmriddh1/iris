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

frameworks are bibles of cybersecurity\
**mitre atlas, owasp top 10 LLM, mitre att&ck, NIST cybersecurity frameworks**

1)  **[MITRE ATLAS (Adversarial Threat Landscape for AI Systems)](https://atlas.mitre.org):**\
   an industry framework for tactics and techniques used by attackers against AI systems, ATLAS recognises publishing hallucinated entities (ID: AML.T0060) as one of its prominent techniques under the resource development (ID: AML.TA0003) objective.

   &emsp;**Tactics:**\
   &emsp;&emsp;a) [Resource Development (AML.TA0003)](https://atlas.mitre.org/tactics/AML.TA0003) for the attacker’s side of the attack\
   &emsp;&emsp;b) [Discovery (AML.TA0008)](https://atlas.mitre.org/tactics/AML.TA0008) for the recon step.

   **Techniques:**\
   &emsp;&emsp;a) [Publishing Hallucinated Entities (ID: AML.T0060)](https://atlas.mitre.org/techniques/AML.T0060)\
   &emsp;&emsp;b) [Discover LLM Hallucinations (AML.T0062)](https://atlas.mitre.org/techniques/AML.T0062)\
   &emsp;&emsp;c) [AI Model Inference API Access (AML.T0040)](https://atlas.mitre.org/techniques/AML.T0040)

**Case Studies:**\
   &emsp;&emsp;[ChatGPT Package Hallucination (AML.CS0022)](https://atlas.mitre.org/studies/AML.CS0022):\
   &emsp;&emsp;&emsp;&emsp;Researchers prompted ChatGPT for package suggestions and identified the non-existent ones. They then uploaded an empty package to PyPI to track downloads.

2) **[OWASP Top 10 for LLM Applications 2025](https://genai.owasp.org/llm-top-10/):**

   open-source, community-voted list of the top 10 most critical security risks in Large Language Models (LLMs) and related applications.

   &emsp;&emsp;a) Supply Chain [(LLM03)](https://genai.owasp.org/llmrisk/llm032025-supply-chain/): the direct, most pressing security risk linked to iris.\
   &emsp;&emsp;b) Misinformation [(LLM09)](https://genai.owasp.org/llmrisk/llm092025-misinformation/): a false but confidently suggested dependency may set as the origin of misinformation.\
   &emsp;&emsp;c) Improper Output Handling [(LLM05)](https://genai.owasp.org/llmrisk/llm052025-improper-output-handling/)

3) [**MITRE ATT&CK (Adversarial Tactics, Techniques, and Common Knowledge):**](https://attack.mitre.org/)

knowledge base of adversary tactics and techniques based on real-world observations. ATT&CK does not model hallucination itself; it covers what happens after a malicious package reaches the developer.

   **Tactics:**\
   &emsp;&emsp;a) [Initial Access (TA0001)](https://attack.mitre.org/tactics/TA0001/) for how the malicious package reaches the developer\
   &emsp;&emsp;b) [Execution (TA0002)](https://attack.mitre.org/tactics/TA0002/) for what runs once it is installed

   **Techniques:**\
   &emsp;&emsp;a) [Supply Chain Compromise (T1195)](https://attack.mitre.org/techniques/T1195/)\
   &emsp;&emsp;b) [Compromise Software Dependencies and Development Tools (T1195.001)](https://attack.mitre.org/techniques/T1195/001/)\
   &emsp;&emsp;c) [Command and Scripting Interpreter (T1059)](https://attack.mitre.org/techniques/T1059/)

   **Case Studies:**\
   &emsp;&emsp;ATT&CK has no case studies; it lists campaigns and procedure examples instead. One example on the [T1195.001](https://attack.mitre.org/techniques/T1195/001/) page is TeamPCP:\
   &emsp;&emsp;&emsp;&emsp;coordinated supply chain attacks on the npm, VS Code, Docker and PyPI ecosystems.

   **Mitigations and Detection:** (listed on the [T1195.001](https://attack.mitre.org/techniques/T1195/001/) page):\
   &emsp;&emsp;a) M1013 Application Developer Guidance: lock dependencies to specific versions\
   &emsp;&emsp;b) M1033 Limit Software Installation: pull from internal repositories of verified, approved packages\
   &emsp;&emsp;c) DET0009 detection strategy: dependency manager activity, then install, first run and outbound traffic

## visit:



## phase wise flow:
 

## architecture:

 
 
## tech stack:
 

  
## abstract:
 

## limitations:


## research papers:
 

## license:
 
MIT — see `LICENSE`.
 
## contributors and project timeline:
created by: samriddhi guha (samriddhiguha777@gmail.com) 

timeline: october 28, 2026 - present

 
