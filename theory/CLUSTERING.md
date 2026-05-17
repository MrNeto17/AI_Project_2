# Unsupervised Learning: Clustering

**Institution:** U. PORTO | FEUP FACULDADE DE ENGENHARIA, UNIVERSIDADE DO PORTO  
**Author:** Carlos Soares (csoares@fe.up.pt)  
**Course Context:** IART @ L.EIC | Page 1

---

## Clustering for Segmentation

* **Target Population:** Customers
* **Transformation Stage 1:** Characterized customers (e.g., age, zip code)
* **Transformation Stage 2:** Customer groups (e.g., bobo's, radical grandparents)

### Technical Graph/Diagram Analysis: Consumer Group Stratification
The slide illustrates a top-down segmentation pipeline utilizing discrete geometric nodes to define data organization:
1.  **Raw Input Layer ("customers"):** Represented as a horizontal linear array of nine uncoloured, uniform grey circular coordinates signifying an un-profiled, high-entropy dataset.
2.  **Feature Assignment Vector:** A downward-pointing block vector arrow leads to the intermediate layer.
3.  **Characterized Representation Layer ("characterized customers e.g. age, zip code"):** The identical linear layout of nodes is now structurally encoded with categorical variations. The nodes are assigned specific high-contrast color values indicating multi-dimensional profiling: Red, Blue, Red, Yellow, Yellow, Blue, Red, Yellow, Blue.
4.  **Partitioning Vector:** A second downward-pointing block vector arrow denotes the execution of a distance-minimizing grouping algorithm.
5.  **Clustered Target Output ("customer groups e.g. bobo's, radical grandparents"):** The nodes are optimally organized into three distinct, non-overlapping topological clusters bounded by explicit oval decision spaces:
    * **Cluster 1 (Left Oval):** Encloses four Red coordinates, representing perfect intra-cluster homogeneity.
    * **Cluster 2 (Center Oval):** Encloses three Blue coordinates, minimizing spatial variance.
    * **Cluster 3 (Right Oval):** Encloses three Yellow coordinates, representing a clean, isolated neighborhood segment.

**Course Context:** IART @ L.EIC | Page 2

---

## Plan

* Clustering
* Evaluation of clusterings
* Clustering methods

**Course Context:** IART @ L.EIC | Page 3

---

## Definition

* Organization of data in groups such that:
    * **High intra-group similarity**
    * **Low between-groups similarity**
* *Informally, find the natural grouping between the elements of a given dataset.*

### Visual Representation Notes
The slide includes multiple realistic visual nodes representing various high-performance and municipal vehicle architectures (such as a blue rally-specification hatchback with gold wheels, a silver and green German "POLIZEI" highway patrol coupe, an open-wheel formula race car, a red classic American muscle coupe, a compact red urban city hatchback, and an American black-and-white police interceptor sedan) to contextualize cross-dimensional classification problems.

**Course Context:** IART @ L.EIC | Page 4

---

## Example (1/2)

* Which "natural clusters" do these clusters represent?

### Technical Layout/Diagram Analysis: Feature Extraction Framework
The slide segments the vehicle imagery matrix into explicit visual arrays to prompt classification hypothesis building:
* **Sub-array 1 ("sports"):** Displays three high-performance vehicles characterized by specialized aerodynamic profiles, performance wheels, and track tuning (the blue rally car, the green-striped police coupe, and the low-slung formula race car).
* **Sub-array 2 ("not sports"):** Isolates three everyday utilitarian transport designs (the red classic touring coupe, the small three-door eco-commuter city car, and the standard high-clearance police interceptor sedan).

**Course Context:** IART @ L.EIC | Page 5

---

## Example (2/2)

* And these?

### Technical Layout/Diagram Analysis: Alternative Attribute Splitting
The same dataset is re-arranged vertically to show multi-axis clustering criteria independent of performance:
* **Column Array 1 ("European"):** Pairs the silver German highway patrol car with the European formula race chassis based on regional engineering origin.
* **Column Array 2 ("Asian"):** Clusters the Japanese rally platform alongside the high-efficiency Asian urban commuter hatchback.
* **Column Array 3 ("American"):** Groups the large-displacement American muscle car with the standard North American black-and-white municipal response cruiser.

**Course Context:** IART @ L.EIC | Page 6

---

## Clustering Selection...

### Technical Graph/Diagram Analysis: Multi-Criteria Decision Tree
The slide features a comprehensive visual system architecture blueprint comparing competing data grouping configurations:
* **Root node:** A centralized blue rectangular frame containing all six vehicle observations in an unclassified matrix.
* **Branching Hyperplanes:** Two large, light blue directional vectors diverge to illustrate different target functions:
    * **Left Branch (Performance Attribute Strategy):** Splits the dataset into two distinct, teal-bordered vertical bounding cards labeled **"Desportivos"** (Sports) and **"Não desportivos"** (Non-sports).
    * **Right Branch (Geographical Origin Strategy):** Divides the identical dataset into three independent, teal-bordered vertical bounding boxes labeled **"Europeus"**, **"Asiáticos"**, and **"Americanos"**.
* **Evaluation Banner:** A wide, solid crimson block spans across the base of both tactical outputs, containing the fundamental algorithmic inquiry text in white: **"which one is best?"**, introducing the core necessity for mathematical clustering evaluation.

**Course Context:** IART @ L.EIC | Page 7

---

## Requires Clustering Evaluation

* Good or bad?

### Diagrammatic Analysis: Ground-Truth Ambiguity
The slide presents an illustration highlighting classification uncertainty. A single vehicle image (the green-striped police patrol car) is centered above a bold textual query asking **"good or bad?"**. This emphasizes that without defined objective functions or external validation metrics, an individual assignment cannot be classified as correct or incorrect.

**Course Context:** IART @ L.EIC | Page 8

---

## Clustering Evaluation

### Technical Evaluation Frameworks

#### Technical / Domain-Specific
* Analyze **intra-segment homogeneity** and **inter-segment heterogeneity**.

#### There are other criteria:
* Relate segments with an **external variable** not used in clustering.
* Analyze **sensitivity of clusters**:
    * Repeat execution of the $K$-means algorithm with different initial centers.
    * Or execute with slightly different samples.
* **Utility** of the clustering to solving the problem it was developed to solve.
    * *Hard to quantify.*
    * Use of external variables is the closest we can get to assessing this utility.

### Technical Graph Analysis: High-Entropy Outlier Identification
The slide displays three black-line circle partitions against a neutral grey background representing evaluation states:
* **Left Partition:** Contains four Red circular nodes arranged tightly, indicating near-zero intra-cluster variance.
* **Center Partition:** Contains three Blue circular nodes alongside a highly prominent, centralized black question mark symbol ($\mathbf{?}$), signaling a structural anomaly, unassigned vector, or low-confidence cluster assignment.
* **Right Partition:** Encloses five Yellow circular nodes uniformly distributed, indicating stable structural convergence.

**Course Context:** IART @ L.EIC | Page 9

---

## Internal Measures: Silhouette Score

* $a(i)$: Average distance between $i$ and all of the other points in its own cluster. *(Cluster labels assigned from ground-truth classes)*
* $b(i)$: Distance between $i$ and its next nearest cluster centroid.
* For a single point, $i$:
    $$\[1em] s(i) = \frac{b(i) - a(i)}{\max\{a(i), b(i)\}} \[1em]$$
* Boundary Constraints: $-1 \le s(i) \le 1$
* **Interpretation Metrics:**
    * Values approaching $-1$: Represent sprawling, overlapped clusters.
    * Values approaching $+1$: Represent tight, well-separated clusters.


**Course Context:** IART @ L.EIC | Page 10

---

## External Measures: General Idea

* Customer clustering on age and income.
* Same clustering… adding churn information.

**Course Context:** IART @ L.EIC | Page 11

---

## External Measures: Jaccard Index

* Number of pairs of examples that align under joint classification properties (e.g., pairs of customers).

### Similarity Mapping Matrix
$$\begin{array}{c|c|c} & \text{Cluster} & \text{Value of External Variable} \\\hline \text{SS} & = & = \\\hline \text{SD} & = & \neq \\\hline \text{DS} & \neq & = \\\hline \text{DD} & \neq & \neq \\ \end{array}$$

$$\[1em] J = \frac{SS}{SS + SD + DS} \[1em]$$

**Course Context:** IART @ L.EIC | Page 12

---

## Todo

* Clustering
* Evaluation of clusterings
* **Clustering methods**
    * Overview of algorithms
    * Distance

**Course Context:** IART @ L.EIC | Page 13

---

## Clustering Algorithms: An Example

*(Placeholder slide tracking runtime traces and iterative clustering execution spaces).*

**Course Context:** IART @ L.EIC | Page 14

---

## Types of Clustering Methods

* **Partitioning:** Multiple object partitions optimized iteratively.
* **Hierarchical:** Hierarchical decomposition of objects according to a certain criterion.
* **Density-based:** Dense groups regardless of the geometric shape.
* **Model-based:** One model for each cluster with parameters adjusted using the source data.

*Question:* Which one to use?

**Course Context:** IART @ L.EIC | Page 15

---

## Know Your Algorithms: K-Means

1.  Initialize the centers of the $k$ groups (e.g., a set of $k$ randomly chosen observations).
2.  **Repeat:**
    * Allocate each observation to the group whose center is nearest.
    * Re-calculate the center of each group.
3.  ...Until the groups are stable (i.e., there is no change, or no significant change in the evaluation criterion).



**Course Context:** IART @ L.EIC | Page 16

---

## Know Your Algorithms: K-Means Pros

* **Availability:** Built into most data analysis software suites.
* **Ease of Use:** Requires only one user-defined hyperparameter ($k$).
* **Efficient:** Computational complexity order is $\mathcal{O}(tkn)$:
    * $n$ is the number of objects, $k$ is the number of clusters, $t$ is the number of iterations.
    * Typically, $k, t \ll n$.
    * *Note:* It often stops in a local optimum; a global optimum may be found by repeated execution.
* **Interpretability:** Centroids directly represent the mathematical cluster profile.

**Course Context:** IART @ L.EIC | Page 17

---

## Know Your Algorithms: K-Means Cons

* **Parameter Dependent:** Necessary to specify in advance the explicit value of $k$ (number of clusters).
* **Stochastic:** Different solutions are obtained with different initial random centers.
* **Local Optima:** Prone to premature convergence (though there are variants based on meta-heuristics to mitigate this).
* **Mutually Exclusive Clusters:** Each client/data node can only belong to exactly one cluster.
* **Variable Type Constraints:** Only natively supports numeric variables:
    * There are variants capable of dealing with nominal variables, but the system must be able to calculate the average object of a set of objects.
* **Assumptions Regarding Data Nature:**
    * Difficulty in dealing effectively with background noise and outliers.
    * Difficulty in identifying clusters with non-convex forms (typically finds clusters strictly with spherical shapes).

**Course Context:** IART @ L.EIC | Page 18

---

## Know Different Algorithms: DBSCAN

*(Core presentation framework highlighting density reachability, core points, border points, and $\epsilon$-neighborhood parameters).*

**Course Context:** IART @ L.EIC | Page 19

---

## Know Your Algorithms: What Changes?

* **K-Means vs. DBSCAN comparison metrics.**

**Course Context:** IART @ L.EIC | Page 20

---

## Todo

* Clustering
* Evaluation of clusterings
* **Clustering methods**
    * Overview of algorithms
    * **Distance**

**Course Context:** IART @ L.EIC | Page 21

---

## Distance Functions: Examples

### Numerical Variables
* **Example:** Euclidean Distance Formula
    $$\[1em] d(x, y) = \sqrt{\sum_{i} (x_i - y_i)^2} \[1em]$$

### Nominal Variables
* **Example:** Equality Distance Metric
    * $p = \text{total number of nominal variables}$
    * $m = \text{number of examples where } x \text{ and } y \text{ have the identical value}$
    $$\[1em] d(x, y) = \frac{p - m}{p} \[1em]$$

**Course Context:** IART @ L.EIC | Page 22

---

## But What Is Similarity?

* **Webster’s Dictionary:** > "The quality or state of being similar; likeness; resemblance; as, a similarity of features."
* *Similarity is hard to define – but we know it when we see it.*

**Course Context:** IART @ L.EIC | Page 23

---

## Conclusions

* Methods to identify objective data partitions.
* Various methods available – distance measurement remains central.
* **Evaluation:** Context is essential.

**Course Context:** IART @ L.EIC | Page 24