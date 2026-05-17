# Introduction to ML

**Institution:** U. PORTO | FEUP FACULDADE DE ENGENHARIA, UNIVERSIDADE DO PORTO  
**Author:** Carlos Soares (csoares@fe.up.pt)  


## Machine Learning Definitions

* **Russell, S. and Norvig, P. (1995):** > "(...) machine learning - subfield of Al concerned with programs that learn from experience."
* **Mitchell, T. (1997):** > "A computer program is said to learn from experience E with respect to some class of tasks T and performance measure P if its performance at tasks in T, as measured by P, improves with experience E."
* **Flach, P. (2012):** > "Machine Learning is the systematic study of algorithms and systems that improve their knowledge or performance with experience"

**Course Context:** IART @ L.EIC | Page 2

---

## ML vs Programming

### Traditional Programming
* **Workflow:** Input Data + Program $
ightarrow$ Computer $
ightarrow$ Output
* **Characteristics (Without Machine Learning):** Requires data and *VERY SPECIFIC INSTRUCTIONS* manually programmed to produce a program that generates a new output from new input.

### Machine Learning
* **Workflow:** Input Data + Output $
ightarrow$ Computer $
ightarrow$ Program
* **Characteristics (With Machine Learning):** The computer takes input data and historical outcomes to automatically learn and generate the program (model), which can then process new inputs to make predictions.

**Course Context:** IART @ L.EIC | Page 3

---

## Some Applications
* **Spam Detection:** An incoming email is fed into a Machine Learning Model, which classifies and routes it into either "Spam" (trash bin) or "Not Spam" (monitored inbox).
* **Credit Scoring:** Assessment of applicant criteria to classify creditworthiness into distinct risk thresholds: *Excellent, Good, Fair, Poor, Bad*.
* **Character Recognition:** * **Handwritten Digits:** Recognition of optical matrix inputs (e.g., sequences like `3134727121`, `1742351244`).
    * **License Plate Recognition:** Segmentation and text conversion of vehicle plates (e.g., extracting `LP 53 569` / `LP53569` from a localized bounding box image).
* **House Prices Prediction:** Regression models mapping geographic and infrastructural features to real estate valuations.

**Course Context:** IART @ L.EIC | Page 4

---

## Main ML Tasks

```
                     ┌───────────────────┐
                     │ Machine Learning  │
                     └─────────┬─────────┘
        ┌──────────────────────┼──────────────────────┐
┌───────▼───────┐      ┌───────▼───────┐      ┌───────▼───────┐
│  Supervised   │      │ Unsupervised  │      │ Reinforcement │
├───────────────┤      ├───────────────┤      ├───────────────┤
│  Task Driven  │      │  Data Driven  │      │  Learn from   │
│(Predict next  │      │  (Identify    │      │   Mistakes    │
│    value)     │      │   Clusters)   │      │               │
└───────────────┘      └───────────────┘      └───────────────┘
```

**Course Context:** IART @ L.EIC | Page 5

---

## ML Tasks: Supervised Learning

### Core Concepts
* **Data:** Labelled examples.
* **Goal:** Predict the label for a new example.
* **Evaluation:** Predicted vs. observed label.

### Technical Graph Analysis: Classification Space
The slide includes a two-dimensional Cartesian coordinate system visualizing a binary classification problem:
* **Axes:** The horizontal axis ($X$) represents **Tumor Size**, and the vertical axis ($Y$) represents **Patient Age**.
* **Data Points:** * **Benign Class:** Represented by open green circles ($\circ$) concentrated in the lower-left quadrant (lower age, smaller tumor size).
    * **Malignant Class:** Represented by red crosses ($	imes$) clustered in the upper-right quadrant (higher age, larger tumor size).
* **Decision Boundary:** A linear separation line (hyperplane in 2D) with a negative slope runs diagonally from the upper-left towards the lower-right. This boundary segments the feature space into two distinct regions to minimize empirical risk, successfully isolating the benign samples from the malignant samples.

### Applications
* Given the size of the tumor and the age of the patient, is the tumor malignant or benign?
* What is the mortality rate of a given disease, according to age group?
* What animal is depicted in the picture?

**Course Context:** IART @ L.EIC | Page 6-7

---

## ML Tasks: Unsupervised Learning

### Core Concepts
* **Data:** Unlabelled examples.
* **Goal:** Find patterns.
* **Evaluation:** Utility of patterns (noting that this is *inherently more difficult to assess*).

### Technical Graph Analysis: DBSCAN Clustering
The slide features side-by-side scatter plots representing exploratory spatial data clustering on an unlabelled metric dataset:
* **Dimensionality:** Both plots map features across a Cartesian space where the $X$-axis scales from $-10$ to $50$ and the $Y$-axis scales from $-10$ to $50$.
* **Left Plot ("Original data set"):** Displays a continuous distribution of unlabelled homogeneous blue coordinates. Visually, there are three high-density regional concentrations alongside multi-scale background noise.
* **Right Plot ("Clusters found by DBSCAN"):** Visualizes the algorithmic output of the Density-Based Spatial Clustering of Applications with Noise (DBSCAN) algorithm:
    * **Cluster 1 (Green):** A highly localized, small, spherical dense cluster centered near coordinate $(0, 25)$.
    * **Cluster 2 (Magenta):** A medium-sized dense cluster centered near $(0, 0)$.
    * **Cluster 3 (Yellow):** A massive, disperse circular cluster spanning across the domain from $X \in [20, 45]$ and $Y \in [10, 35]$.
    * **Noise/Outliers (Light Cyan / Grey triangles):** Low-density background points isolated outside the topological reach of the core density thresholds ($\epsilon$ neighborhoods and minimum points criteria), left unassigned to any cluster color.

### Applications
* What types of Netflix client are there?
* Which products are often purchased together with milk?
* Which communities exist in a given social network?

**Course Context:** IART @ L.EIC | Page 8-9

---

## Main ML Tasks: Reinforcement Learning

### Core Concepts
* **Data:** Sequences of states of the world, sequences of actions, and final outcomes.
* **Goal:** Find the optimal policy ($\pi^*$), which represents a mapping of states to actions.
* **Learning:** Reinforcing/rewarding actions considered positive; punishing actions considered negative.
* **Evaluation:** Final outcome is typically only available at the end of an episode.
* **Reward Function:** Estimation of the contribution of a specific intermediate action to a successful final outcome.

### Technical Graph/Diagram Analysis: Agent-Environment Loop (AlphaGo)
The document provides a systems architecture block diagram illustrating a closed-loop Markov Decision Process (MDP) instantiated by DeepMind's AlphaGo:
1.  **Environment:** Represented by the state of the Go board game.
2.  **Observation / State ($S_t$):** The environment emits the current visual state topology of the board grid to the learning agent.
3.  **Agent (AlphaGo):** The deep reinforcement learning model processes the observation through its policy network.
4.  **Action ($A_t$):** AlphaGo executes an action, computing and applying the "Next Move" marker onto the corresponding coordinate space of the board.
5.  **Reward ($R_t$):** The environment evaluates the resulting state changes against a goal function and feeds back a scalar reward or penalty signal into AlphaGo to update its value/policy parameters.

### Applications
* Teach a robot to find the best trajectory between two points (by rewarding reduced distance to goal and punishing increased distance to goal).
* Given the rules of a game (e.g., chess, go), learn how to play it competitively.

**Course Context:** IART @ L.EIC | Page 10-11