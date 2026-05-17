# Introduction to Classification

**Institution:** U. PORTO | FEUP FACULDADE DE ENGENHARIA, UNIVERSIDADE DO PORTO  
**Author:** Carlos Soares (csoares@fe.up.pt)   
**Course Context:** IART @ L.EIC | Page 1

---

## Plan & Goals

### Plan
* **Introduction:** what and what for
* **Data:** an example
* **An example model:** decision trees
    * how to interpret
    * how to use
* **Evaluation:**
    * how to quantify the accuracy of predictions
    * how to estimate the accuracy of prediction past data
* **Algorithms:**
    * decision tree learning
    * overview of other algorithms
* **Reference materials:** R&N: 19-19.4

### Goals
* Identify problems where classification is useful
* Identify relevant data
* Know how to analyze and use a decision tree
* Superficially understand the decision tree learning algorithm and its limitations
* Know how to quantify and estimate the predictive performance of a model
* Superficially understand the differences between algorithms

**Course Context:** IART @ L.EIC | Page 2

---

## Classification for Targeting

* **Existing Database:** * Customers who bought
    * Customers who didn't buy
* **Target Mapping Stage:** * Processing historical consumer binary categories via a classification engine.
* **Predictive Pipeline Output:**
    * Scoring "New Customers" to isolate high-probability buyers from non-buyers.

### Technical Graph/Diagram Analysis: Targeting Pipeline
The slide utilizes an abstract workflow schematic tracking data state updates:
1.  **Input Layer:** A heterogeneous mixture of green human silhouettes (representing "customers who bought") and red human silhouettes (representing "customers who didn't buy").
2.  **Transformation Hyperplane:** An arrow points through a predictive block diagram representing an algorithmic classification model.
3.  **Target Output Layer:** A secondary set of grey silhouettes ("new customers") are systematically partitioned. The model isolates individual nodes into high-value target spaces based on structural similarity matrices compiled from historical buyer feature dimensions.

**Course Context:** IART @ L.EIC | Page 3

---

## The Classification Problem

* **Given:**
    * A description of an object, $x \in X$
    * A fixed, predefined set of categories (classes, labels), $Y = \{y_1, y_2, \dots, y_k\}$
* **Goal:**
    * Predict which category $x$ belongs to: $f(x) \in Y$
* **Learning (Induction):**
    * Given a set of labeled examples, $D = \{(x_1, y_1), (x_2, y_2), \dots, (x_n, y_n)\}$
    * Find a function (classifier/model) $f(x)$ that generalizes well to unseen examples.

**Course Context:** IART @ L.EIC | Page 4

---

## Example Problems

* **Medical Diagnosis:** Given patient attributes (symptoms, lab results) $\rightarrow$ Predict disease state (e.g., *Healthy*, *Influenza*, *Pneumonia*).
* **Text Classification:** Given an electronic document or email text $\rightarrow$ Predict categorization folder (e.g., *Spam*, *Ham*, *Financial*, *Personal*).
* **Fraud Detection:** Given transaction attributes (amount, location, velocity) $\rightarrow$ Predict legitimacy state (*Legitimate*, *Fraudulent*).
* **Image Recognition:** Given raw pixel matrices $\rightarrow$ Predict specific target presence (*Cat*, *Dog*, *Car*, *Pedestrian*).

**Course Context:** IART @ L.EIC | Page 5

---

## Data for Classification

* **Dataset (D):** Composed of observations/examples.
* **An Example/Observation:**
    * Described by **Features/Attributes** ($X$):
        * Predictors / Independent variables.
        * Can be numerical (continuous/discrete) or nominal (categorical).
    * Described by a **Target / Class Label** ($Y$):
        * The variable to predict / Dependent variable.
        * Categorical with discrete, non-overlapping values.

### Historical Example Table Matrix
$$\begin{array}{c|c|c|c|c} \textbf{ID} & \textbf{Age (Years)} & \textbf{Income (\$)} & \textbf{Credit Score} & \textbf{Class: Defaulted?} \\\hline 1 & 35 & 45,000 & \text{Fair} & \text{No} \\\hline 2 & 22 & 22,000 & \text{Poor} & \text{Yes} \\\hline 3 & 48 & 85,000 & \text{Excellent} & \text{No} \\\hline 4 & 55 & 32,000 & \text{Good} & \text{No} \\\hline 5 & 29 & 61,000 & \text{Fair} & \text{Yes} \\ \end{array}$$

**Course Context:** IART @ L.EIC | Page 6

---

## Running (Hopping?) Example

* **Problem Statement:** Classify incoming insect specimens into one of two distinct biological classes based on morphological feature vectors.
* **Target Classes ($Y$):**
    * **Grasshoppers** (Chorthippus paralellus)
    * **Katydids** (Conocephalus discolor)
* **Feature Space dimensions ($X$):**
    * $x_1$: **Abdomen Length** (measured in millimeters)
    * $x_2$: **Antenna Length** (measured in millimeters)

**Course Context:** IART @ L.EIC | Page 7

---

## Dataset: Grasshoppers vs Katydids

Here is the morphological measurements matrix for $n = 12$ captured specimens:

$$\begin{array}{c|c|c|c} \textbf{Specimen ID} & \textbf{Abdomen Length (mm)} & \textbf{Antenna Length (mm)} & \textbf{Species Label} \\\hline 1 & 1.1 & 7.1 & \text{Grasshopper} \\\hline 2 & 1.7 & 6.2 & \text{Grasshopper} \\\hline 3 & 2.4 & 5.1 & \text{Grasshopper} \\\hline 4 & 1.9 & 4.9 & \text{Grasshopper} \\\hline 5 & 2.5 & 4.1 & \text{Grasshopper} \\\hline 6 & 3.2 & 4.8 & \text{Grasshopper} \\\hline 7 & 5.1 & 8.2 & \text{Katydid} \\\hline 8 & 5.7 & 7.6 & \text{Katydid} \\\hline 9 & 6.4 & 6.9 & \text{Katydid} \\\hline 10 & 7.2 & 8.0 & \text{Katydid} \\\hline 11 & 8.1 & 7.1 & \text{Katydid} \\\hline 12 & 8.9 & 6.2 & \text{Katydid} \\ \end{array}$$

**Course Context:** IART @ L.EIC | Page 8

---

## Visualizing the Data Space

### Technical Graph Analysis: Biological Feature Metric Space
The slide features a 2D scatter plot visualizing the distribution of the insect dataset:
* **Horizontal Axis ($X$):** Abdomen Length (mm), scaling linearly from $0$ to $10$.
* **Vertical Axis ($Y$):** Antenna Length (mm), scaling linearly from $0$ to $10$.
* **Data Class Distribution:**
    * **Grasshoppers:** Plotted as light-green filled circular markers clustered securely in the lower-left domain region (Abdomen values $< 4.0\text{mm}$, Antenna values generally $< 7.5\text{mm}$).
    * **Katydids:** Plotted as dark-red filled triangular markers clustered in the right hemisphere of the coordinate space (Abdomen values $> 5.0\text{mm}$, Antenna values spanning from $6.0\text{mm}$ to $8.5\text{mm}$).
* **Spatial Characteristics:** The dataset exhibits a clear spatial partition margin along the Abdomen Length axis, representing a highly separable binary classification layout.

**Course Context:** IART @ L.EIC | Page 9

---

## Classifier Models: Overview

* **What is a Model?** A representation or hypothesis explaining the structural mapping between feature fields and target labels.
* **Types of Classifiers:**
    * **Geometric Models:** Hyperplanes, decision boundaries (e.g., SVMs, Linear Discriminants).
    * **Probabilistic Models:** Conditional probability tables (e.g., Naive Bayes, Logistic Regression).
    * **Logical Models:** Hierarchical rule conditional sets (e.g., **Decision Trees**, Rule Induction).

**Course Context:** IART @ L.EIC | Page 10

---

## Decision Trees: An Introduction

* A logical model structured as a hierarchical tree.
* **Internal Nodes:** Represent a logical conditional check on a specific feature attribute.
* **Branches:** Represent the corresponding outcome values of the conditional split check.
* **Leaf Nodes:** Represent terminal class predictions/labels.

**Course Context:** IART @ L.EIC | Page 11

---

## Example Decision Tree

Below is the generated Decision Tree model for our insect classification task:

```
                  [ Abdomen Length > 4.0 mm ]
                         /         \
                       No/           \Yes
                      /               \
            [ Grasshopper ]       [ Antenna Length > 6.0 mm ]
                                          /         \
                                        No/           \Yes
                                         /             \
                                   [ Grasshopper ]  [ Katydid ]
```

**Course Context:** IART @ L.EIC | Page 12

---

## Interpreting the Decision Tree

* **Root Condition:** Evaluate if the incoming insect specimen has an `Abdomen Length` strictly greater than $4.0\text{mm}$.
    * If **No**: The tree terminates immediately into a leaf predicting **Grasshopper**.
    * If **Yes**: A second level condition is evaluated.
* **Level 2 Condition:** Evaluate if the `Antenna Length` is strictly greater than $6.0\text{mm}$.
    * If **No**: Terminate to a leaf predicting **Grasshopper**.
    * If **Yes**: Terminate to a leaf predicting **Katydid**.

**Course Context:** IART @ L.EIC | Page 13

---

## How Decision Trees Partition the Feature Space

### Technical Graph Analysis: Hierarchical Axis-Parallel Decision Spaces
The slide illustrates the geometric interpretation of the decision tree model mapped onto the 2D insect measurement plane:
* **Axes:** $X$-axis represents Abdomen Length ($0$ to $10\text{mm}$), $Y$-axis represents Antenna Length ($0$ to $10\text{mm}$).
* **First Decision Boundary (Split 1):** A vertical line is drawn at $X = 4.0$. This splits the feature space into:
    * Left Region ($X \le 4.0$): Designated entirely as **Grasshopper** space.
    * Right Region ($X > 4.0$): Subjected to secondary conditional validation.
* **Second Decision Boundary (Split 2):** Within the right hemisphere ($X > 4.0$), a horizontal line is constructed at $Y = 6.0$. This subdivides the right region into:
    * Lower-Right Rectangular Subspace ($X > 4.0$ and $Y \le 6.0$): Classified as **Grasshopper**.
    * Upper-Right Rectangular Subspace ($X > 4.0$ and $Y > 6.0$): Classified as **Katydid**.
* **Geometric Feature:** The decision tree constructs hyperrectangles by drawing axis-parallel boundaries to isolate data classes.

**Course Context:** IART @ L.EIC | Page 14

---

## Using the Model for Prediction

Let's apply our decision tree model to classify an unlabelled test specimen:
* **New Unseen Specimen Vector:** `(Abdomen Length = 6.0 mm, Antenna Length = 5.5 mm)`

### Execution Trace through the Tree:
1.  Check `Abdomen Length > 4.0 mm` $\rightarrow$ $6.0 > 4.0$ $\rightarrow$ **Yes** (Follow right branch).
2.  Check `Antenna Length > 6.0 mm` $\rightarrow$ $5.5 > 6.0$ $\rightarrow$ **No** (Follow left branch).
3.  Reach Terminal Leaf $\rightarrow$ Predicted Label is **Grasshopper**.

**Course Context:** IART @ L.EIC | Page 15

---

## Quantifying Model Performance: Evaluation Metrics

To understand if our induction model is accurate, we construct a verification index matrix comparing actual labels vs predicted labels.

### The Confusion Matrix Layout
$$\begin{array}{c|c|c} & \textbf{Predicted: POSITIVE} & \textbf{Predicted: NEGATIVE} \\\hline \textbf{Actual: POSITIVE} & \text{True Positive (TP)} & \text{False Negative (FN)} \\\hline \textbf{Actual: NEGATIVE} & \text{False Positive (FP)} & \text{True Negative (TN)} \\ \end{array}$$

### Derived Core Metrics
* **Accuracy:** Overall proportion of correct predictions made by the model.
    $$\[1em] \text{Accuracy} = \frac{TP + TN}{TP + TN + FP + FN} \[1em]$$
* **Error Rate:** Complement of accuracy.
    $$\[1em] \text{Error Rate} = 1 - \text{Accuracy} = \frac{FP + FN}{TP + TN + FP + FN} \[1em]$$

**Course Context:** IART @ L.EIC | Page 16-17

---

## Detailed Classification Metrics

Depending on application demands, accuracy can be decomposed into localized rates:

* **Precision (Positive Predictive Value):** Exactness measure; when it predicts positive, how often is it correct?
    $$\[1em] \text{Precision} = \frac{TP}{TP + FP} \[1em]$$
* **Recall / Sensitivity (True Positive Rate):** Completeness measure; what percentage of actual positive cases did the model capture?
    $$\[1em] \text{Recall} = \frac{TP}{TP + FN} \[1em]$$
* **F1-Score:** Harmonic mean combining Precision and Recall into a balanced metric index.
    $$\[1em] \text{F1-Score} = 2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}} \[1em]$$

**Course Context:** IART @ L.EIC | Page 18

---

## Data Splitting: Training vs Testing

* **Golden Rule of ML Evaluation:** *Never evaluate a model's predictive performance on the same dataset used to train it.* This causes overfitting and unrealistic performance expectations.
* **The Solution: Train/Test Split**
    * **Training Set:** Used by the learning algorithm to construct and adjust the model parameters.
    * **Testing Set:** Kept hidden during learning. Used exclusively to evaluate the final model's generalization capabilities.

**Course Context:** IART @ L.EIC | Page 19

---

## Overfitting in Machine Learning

* **Definition:** Overfitting occurs when an algorithm models the training data too closely, learning its specific random noise and anomalies rather than the underlying general trend.
* **Symptoms:** Highly superior performance (e.g., $100\%$ accuracy) on the training set, but highly degraded performance on the unseen test set.

**Course Context:** IART @ L.EIC | Page 20

---

## How Decision Tree Induction Works

How do we automatically construct a decision tree from raw historical arrays? We use a top-down greedy recursive partitioning approach.

### Top-Down Induction Principles:
1.  Start at the root node containing all training instances.
2.  Evaluate all available feature attributes and select the "best split variable" that maximizes information purity.
3.  Partition the dataset into sub-nodes according to the split criteria.
4.  Recursively repeat the step for each branch until stopping criteria are satisfied (e.g., absolute leaf purity reached, or maximum depth limit encountered).

**Course Context:** IART @ L.EIC | Page 21

---

## Selecting the Best Split: Information Gain

To choose the optimal feature split attribute, we measure the reduction in entropy (disorder/purity loss).

### Entropy Equation
For a dataset $S$ containing a binary distribution of positive ($p_+$) and negative ($p_-$) targets:
$$\[1em] \text{Entropy}(S) = -p_+ \log_2(p_+) - p_- \log_2(p_-) \[1em]$$

### Information Gain Equation
$$\[1em] \text{Gain}(S, A) = \text{Entropy}(S) - \sum_{v \in \text{Values}(A)} \frac{|S_v|}{|S|} \text{Entropy}(S_v) \[1em]$$
The attribute $A$ yielding the maximum Information Gain is selected as the branching node parameter.

**Course Context:** IART @ L.EIC | Page 22

---

## Information Gain Calculation Example

*(Tracking computational entropy shifts across categorical node splitting states).*

**Course Context:** IART @ L.EIC | Page 23

---

## Alternative Splitting Criteria: Gini Impurity

Another popular structural metric used by algorithms like CART (Classification and Regression Trees) is Gini Impurity.

### Gini Impurity Equation
$$\[1em] \text{Gini}(S) = 1 - \sum_{i=1}^{k} (p_i)^2 \[1em]$$
Where $p_i$ is the probability of an item belonging to class $i$ inside the node. A completely pure node has a Gini index of $0$.

**Course Context:** IART @ L.EIC | Page 24

---

## Tree Pruning: Mitigating Overfitting

To prevent a decision tree from growing infinitely complex and overfitting data noise, we apply pruning strategies:

* **Pre-pruning (Early Stopping):** Halt tree expansion before it creates low-significance nodes (e.g., limit maximum tree depth, set minimum sample threshold per leaf).
* **Post-pruning:** Allow the tree to completely grow to its full complexity, and then systematically collapse bottom-level nodes into sub-leaves if the performance degradation on a validation validation set is negligible.

**Course Context:** IART @ L.EIC | Page 25

---

## Advanced Validation: K-Fold Cross-Validation

When dataset instances are limited, a simple train/test split can be biased. We implement $K$-Fold Cross-Validation:

1.  Partition the complete dataset $D$ into $K$ equally sized, mutually exclusive subsets (folds).
2.  Iterate through $K$ separate validation loops.
3.  In loop $i$, subset $i$ is held out as the testing dataset, and the remaining $K-1$ folds are aggregated to form the training dataset.
4.  Train the model, evaluate metrics, and cache accuracy.
5.  After completing all folds, compute the mean performance index across all $K$ test runs.

**Course Context:** IART @ L.EIC | Page 26

---

## Hyperparameter vs. Error Trajectory

### Technical Graph Analysis: Overfitting Optimization Curve
The slide features an evaluation graph tracking model error rates as a function of decision tree architectural complexity:
* **Horizontal Axis ($X$):** A decision tree hyperparameter (e.g., maximum depth or node size limits), scaling from high complexity on the left ($4, 3, 2$) down to low complexity on the right ($1$).
* **Vertical Axis ($Y$):** Error percentage ($\text{erro \%}$), scaling linearly from $0\%$ to $35\%$.
* **The Curves Matrix:**
    * **Training Error Curve (\text{treino}):** Plotted as a blue dashed curve. It begins extremely low near $0\%$ error at high tree complexity and increases steadily as the hyperparameter forces simpler, shallower tree architectures.
    * **Testing Error Curve (\text{teste}):** Plotted as a solid dark-orange curve. At extreme tree complexity, it exhibits an elevated error rate (highlighting the **Overfitting Zone**). As complexity decreases, the testing error curve drops to a global minimum point. Moving past this optimal window towards over-simplification (under-fitting zone), the testing error spikes upward, aligning closely with the training error curve.
* **Technical Takeaway:** The graph demonstrates empirical validation selection; the optimal hyperparameter choice sits at the valley bottom of the testing error curve where generalization is maximized.

**Course Context:** IART @ L.EIC | Page 27

---

## Model Selection Practice Challenge

### Technical Graph Analysis: Complex Boundary Classification Layout
The slide shows a realistic scatter plot tracking non-linearly separated biological data:
* **Axes:** Abdomen Length on $X$-axis ($0$ to $10$), Antenna Length on $Y$-axis ($0$ to $10$).
* **Data Point Matrix:** * A cluster of light-green circular dots (Grasshoppers) dominates the lower-left.
    * A cluster of dark-red triangle nodes (Katydids) dominates the upper right.
    * **Anomalous Intrusion:** Crucially, a single dark-red Katydid triangle node is located deep inside the green neighborhood at coordinates $(2.1, 1.8)$, and a single light-green Grasshopper circular marker is embedded inside the red neighborhood at $(7.4, 8.2)$.
* **Core Question:** The slide poses an implicit structural question: *Should a model build highly convoluted boundaries to correctly capture these two outlier points, or ignore them to maintain generalization?*

**Course Context:** IART @ L.EIC | Page 28

---

## Ross Quinlan's Algorithmic Vision

* **Context:** Features a tribute note highlighting Ross Quinlan, the foundational computer scientist who developed the pioneering C4.5 and ID3 decision tree induction algorithms.

### Technical Model Mapping Analysis: Quinlan's Classifier Space
The slide overlays a standard C4.5 axis-parallel rule architecture onto the complex dataset:
* **The Logic Model:** ```
    Abdomen Length > 7.1?
       /       \
     No/         \Yes
    /             \
    [ Antenna Length > 6.0? ]    [ Katydid ]
       /       \
     No/         \Yes
    /             \
    [ Katydid ]   [ Grasshopper ]
    ```
* **Geometric Plane Output:** The algorithm constructs an orthogonal boundary split exactly at `Abdomen Length = 7.1` and `Antenna Length = 6.0`. It intentionally isolates the global macroscopic distribution trends while allowing minor localized outlier points to be misclassified, ensuring high test generalization performance.

**Course Context:** IART @ L.EIC | Page 29

---

## Review of Alternative Classification Algorithms

Beyond Decision Trees, multiple classifier structural approaches exist in the industry:

* **K-Nearest Neighbors (KNN):** Instance-based lazy learner that classifies an unseen point based on a majority vote of its closest $K$ metric neighbors.
* **Support Vector Machines (SVM):** Constructs optimal separating hyperplanes maximizing the margin distance between boundary support vectors.
* **Naive Bayes:** Probabilistic classifier utilizing Bayes' Theorem under strict feature independence assumptions.
* **Logistic Regression:** Models class probabilities using a sigmoidal logistic function.
* **Random Forests / Ensemble Methods:** Aggregates predictions across a diverse forest of independent decision trees to reduce overall variance.



**Course Context:** IART @ L.EIC | Page 30

---

## Decision Trees: Pros & Cons

### Pros
* **Learn Hyperrectangles:** Clear orthogonal boundary segmentations.
* **High Interpretability:** Extremely easy to read, visualize, and explain to non-technical stakeholders without mathematical conversion.
* **Robust Data Handling:** Robust against missing attributes and handles multi-scale features without mandatory normalization transformations.
* **Computational Efficiency:** Fast predictive classification runtime order.

### Cons
* **High Variance:** Small changes in the training data distribution can result in a completely different tree architecture.
* **Axis-Parallel Restrictions:** Struggles with complex diagonal decision boundaries, requiring deep nested structures to approximate simple diagonal lines.
* **Greedy Nature:** Prone to settling in local optima because splits are decided step-by-step without looking forward.

**Course Context:** IART @ L.EIC | Page 31