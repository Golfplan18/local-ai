---
lens_id: cleveland-mcgill-perceptual-tasks
name: Cleveland-McGill Perceptual Tasks
lens_type: rubric
applicability: [information-density]
foundational: true
source: "Cleveland, William S., and Robert McGill (1984). Graphical perception: Theory, experimentation, and application to the development of graphical methods. Journal of the American Statistical Association 79(387):531-554. Cleveland, William S. (1985). The Elements of Graphing Data. Wadsworth."
date created: 2026-05-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - rubric
  - visualization
  - perception
  - information-design
---

# Cleveland-McGill Perceptual Tasks

## Trigger

Invoked from within `information-density` (T19) when that mode needs the empirical ranking of how accurately viewers extract quantitative information from each elementary visual encoding — the experimental complement to the Bertin variable catalog. The host mode supplies a graphic in which a quantitative dimension is being encoded in a particular visual form (position on a common scale, length, angle, area, color saturation, etc.); the lens supplies the ten-task ranking with the empirical accuracy basis from Cleveland and McGill's 1984 experiments and successor work, so the analyst can grade the chosen encoding against alternatives and recommend the encoding that best matches the precision the analytical task requires. The output is a per-encoding accuracy grade, a recommended re-encoding when a higher-ranked task is available, and a justified deviation when the chosen encoding is correct despite being lower-ranked (e.g., for spatial-context reasons on a map).

## Core Structure

Cleveland and McGill (1984) decomposed the act of reading a chart into ten elementary perceptual tasks, ranked them experimentally by accuracy of magnitude estimation, and demonstrated that chart designers can systematically improve communication accuracy by choosing higher-ranked encodings when the task is to convey quantitative magnitudes accurately. The ranking is not a directive — sometimes a lower-ranked encoding is correct because of spatial, contextual, or convention-based requirements — but it is the evidentiary baseline against which encoding choices should be defended. The ranking groups closely-rated tasks; within a group, differences are smaller than between groups.

The rubric: each row gives the rank, the task definition, the example chart type that primarily uses it, and the empirical basis (the Cleveland-McGill experimental finding plus relevant successor evidence). Tasks are ordered from most accurate (rank 1) to least accurate (rank 6, with subdivisions where the empirical evidence supports them).

| Rank | Task | Example chart type | Accuracy basis |
|---|---|---|---|
| 1 | Position on a common scale | Bar chart, dot plot, scatterplot (one axis) | Cleveland & McGill (1984) Experiment 1: lowest median absolute error across all tasks tested. Viewers can compare two values on a shared axis with high precision because the scale provides a continuous reference. |
| 2 | Position on non-aligned (parallel) scales | Side-by-side small multiples with separate scales; back-to-back bar charts with separate scales | Cleveland & McGill (1984) Experiment 1: error increases relative to common-scale comparison because viewers must mentally align the scales; precision is reduced but remains substantially better than non-position encodings. |
| 3 | Length, direction, or angle | Stacked bar chart (where length of segment is read), pie chart (angle), clock-face displays (direction) | Cleveland & McGill (1984) Experiment 1 and 2: bar segments not anchored to a common baseline are read with greater error than position-on-common-scale; pie-chart angles are read with comparable error to length without baseline. Heer & Bostock (2010) replicated the ranking on Mechanical Turk. |
| 4 | Area | Bubble chart (circle area), treemap (rectangle area), proportional-symbol map | Cleveland & McGill (1984) Experiment 2: viewers systematically underestimate area differences (Stevens' power law: perceived area scales as actual^0.7 approximately). Error is substantially larger than length-based encodings. |
| 5 | Volume or curvature | 3D bar chart (cube volume), 3D bubble chart (sphere volume), curvature in plot lines | Cleveland & McGill (1984) and Stevens (1957) on volume perception: perceived volume scales as actual^0.5 to 0.6, producing even larger underestimation than area. Curvature comparisons are similarly imprecise. |
| 6a | Color shading or value (lightness) | Choropleth map with sequential lightness, heatmap | Cleveland & McGill (1984) Experiment 3: viewers can rank lightness reliably but cannot extract precise magnitudes; useful for ordinal communication, weak for quantitative magnitude estimation. |
| 6b | Color hue | Categorical-hue choropleth, qualitative-palette charts | Hue carries no inherent quantitative meaning; magnitude estimation from hue alone is essentially arbitrary. Ranks at the bottom for quantitative tasks. (Note: "rainbow" colormaps that vary hue without varying lightness systematically produce magnitude-estimation errors and should be avoided for quantitative encoding.) |
| 6c | Density (texture) | Cross-hatch density fills, dot-density maps | Cleveland & McGill (1984) treated density similarly to lightness; ordinal but not quantitatively precise. Useful in color-unavailable media; otherwise outperformed by lightness. |

The grouping of tasks 6a–6c into a single rank reflects that all three are read with substantially less precision than tasks 1–4 and serve different purposes: lightness for sequential ordinal encoding; hue for categorical encoding; density for media without color. None is an accurate vehicle for quantitative magnitude communication when a higher-ranked alternative is feasible.

### Worked exemplars

**Positive exemplar — choosing rank 1 over rank 4:** A dataset shows population by region. The default infographic uses circle area on a map (rank 4). The redesign replaces the circles with a bar chart sorted by population (rank 1). The bar chart loses the spatial-context information the map provided but gains substantial accuracy in magnitude communication. Whether the redesign is correct depends on whether the spatial context or the magnitude communication is the analytical priority — but the accuracy trade-off should be made explicitly, not by default.

**Negative exemplar — defaulting to rank 4 without justification:** A dashboard reports revenue by product line as a 3D pie chart (rank 5 — angle plus volume cues plus perspective distortion). A simple bar chart (rank 1) would communicate the same information with substantially higher accuracy. The choice of pie chart is unjustified by spatial context, convention, or any analytical requirement; it is chartjunk-adjacent and should be replaced.

**Justified deviation — rank 4 chosen for spatial context:** A map of US states colored by median income uses a sequential lightness colormap (rank 6a). A bar chart of states (rank 1) would communicate income magnitudes with higher accuracy, but would lose the spatial pattern (regional clustering of high-income states) that is the analytical priority. The choropleth's lower rank is justified by the spatial context the map provides; the deviation should be acknowledged and the limited magnitude precision noted.

### Subsequent empirical work

Heer and Bostock (2010) replicated the Cleveland-McGill ranking with Mechanical Turk subjects, confirming the ordering for the tasks tested and extending it to additional encodings (rectangular vs. circular area; donut vs. pie). Talbot, Setlur, and Anand (2014) tested bar-chart variants and confirmed that the addition of any non-position visual cue (3D, gradient fills, perspective) typically reduces magnitude-estimation accuracy without compensating gain. The ranking is robust across replications when the experimental task is straightforward magnitude estimation; in tasks involving pattern recognition, anomaly detection, or trend reading, the relative ordering can shift (a colormap can outperform a long bar chart at gestalt pattern detection, even though bars outperform at point-magnitude estimation).

## Application Steps

1. Receive the graphic from the host mode and identify each quantitative dimension being encoded.
2. For each dimension, identify the perceptual task the viewer must perform to extract the magnitude (position on common scale, length without baseline, angle, area, etc.).
3. Locate the task in the ranking; record its rank.
4. Identify higher-ranked alternative tasks that could encode the same dimension; consider whether the redesign would be feasible given the graphic's purpose, medium, and conventions.
5. Recommend re-encoding to the highest-ranked task that the graphic's constraints permit; when a lower-ranked task is retained, name the constraint that justifies the deviation (spatial context, convention, audience expectation, medium limit).
6. Flag any quantitative claim being made on the basis of a rank-4-or-lower encoding without explicit acknowledgment of the perceptual-accuracy limitations.
7. Return the per-dimension rank assessment, the re-encoding recommendations, the justified-deviation acknowledgments, and the perceptual-accuracy flags to the host mode.

## Detection Signals

- A graphic uses pie charts, bubble charts, 3D effects, area-based encodings, or color-only quantitative encodings; rank-4-or-lower tasks are doing significant analytical work.
- The host mode `information-density` is dispatching and the dispatch invokes this lens.
- A magnitude comparison is being claimed in the analysis but the chart's encoding does not support the precision the claim implies.
- A choropleth map or heatmap is being used to communicate quantitative magnitudes (not just spatial patterns) without acknowledgment of the precision penalty.
- A redesign of a chart is being considered and the analyst needs the empirical ranking to choose among alternatives.
- An audience is expected to extract precise values from a graphic but the encoding is ranked low for accuracy.

## Critical Questions

- Has the perceptual task actually been identified, or is the analyst evaluating the chart-type label without parsing what the viewer must do to read it?
- Is the ranking being used as a directive ("never use pie charts") or as a defeasible guide ("prefer higher ranks unless the lower rank is justified by other considerations")? The latter is correct.
- When a lower-ranked encoding is retained, has the constraint that justifies it been named and weighed against the precision cost?
- Is the analytical task one for which the ranking applies (point-magnitude estimation), or one where the ranking can shift (gestalt pattern detection, anomaly visibility)?
- Has the analyst considered that the ranking is for quantitative magnitude estimation specifically; for nominal-category encoding, the ranking has limited bearing?
- Is the chosen encoding being defended on grounds (convention, aesthetics, audience expectation) that should be acknowledged as compromises rather than as encoding strengths?

## Common Failure Modes

- **Pie-chart-as-default** — using pie charts (rank 3, sometimes plus 3D and perspective penalties) for quantitative comparisons that bar charts (rank 1) would communicate substantially more accurately. Detection: the chart asks viewers to compare two slices' angles when they could be comparing two bars' positions. Correction: replace with a bar chart unless a specific conventional or contextual reason justifies the pie chart.
- **3D-as-impression** — adding 3D effects to bar or pie charts in the belief that 3D improves communication. Detection: the chart includes 3D but the underlying data are two-dimensional. Correction: remove the 3D effect; the perspective distortion lowers rank without analytical compensation.
- **Area-as-quantitative-without-acknowledgment** — using bubble charts or area-based encodings to communicate magnitudes without acknowledging the systematic underestimation viewers will perform. Detection: the chart's caption or accompanying text claims magnitude relationships that viewers cannot accurately extract from area. Correction: include a legend with explicit area-to-magnitude mapping, or replace with a length-based encoding.
- **Color-only quantitative encoding** — relying on color hue alone to communicate magnitude. Detection: the colormap varies hue without varying value, and viewers are expected to read magnitudes from hue. Correction: use a perceptually-uniform sequential colormap (viridis, magma, gray-scale variants) that varies lightness alongside hue, providing the rank-6a perceptual cue rather than the rank-6b arbitrary one.
- **Ranking-as-absolute** — applying the ranking mechanically without considering when lower-ranked encodings are justified by spatial context, convention, or analytical task. Detection: the recommendation strips a choropleth map of its spatial context to gain rank-1 accuracy. Correction: use the ranking as a defeasible guide; preserve lower-ranked encodings when the constraints justify them, but acknowledge the precision compromise.
- **Misidentifying the perceptual task** — categorizing a chart by chart-type label rather than by what the viewer actually does to read it. Detection: the analyst rates a stacked bar chart as rank 1 (position on common scale) when only the bottom segment is anchored to the baseline; segments above the bottom require length-without-baseline reading (rank 3). Correction: parse the actual task per data dimension; a single chart often combines tasks of different ranks.

## Source Citations

- Cleveland, William S., and Robert McGill (1984). "Graphical perception: Theory, experimentation, and application to the development of graphical methods." *Journal of the American Statistical Association* 79(387):531–554. The foundational empirical paper establishing the ten-task ranking through controlled magnitude-estimation experiments.
- Cleveland, William S. (1985). *The Elements of Graphing Data*. Wadsworth (revised edition Hobart Press, 1994). Book-length treatment integrating the ranking into a comprehensive graphing methodology with applied recommendations.
- Cleveland, William S., and Robert McGill (1985). "Graphical perception and graphical methods for analyzing scientific data." *Science* 229(4716):828–833. Wider-audience exposition of the ranking and its scientific-communication implications.
- Heer, Jeffrey, and Michael Bostock (2010). "Crowdsourcing graphical perception: Using Mechanical Turk to assess visualization design." *Proceedings of CHI 2010* 203–212. Replicates the Cleveland-McGill ranking with crowdsourced subjects and extends it to additional encodings.
- Talbot, Justin, Vidya Setlur, and Anushka Anand (2014). "Four experiments on the perception of bar charts." *IEEE Transactions on Visualization and Computer Graphics* 20(12):2152–2160. Tests bar-chart variants and confirms the cost of non-position visual additions.
- Stevens, S.S. (1957). "On the psychophysical law." *Psychological Review* 64(3):153–181. The foundational psychophysics paper establishing power-law relationships between perceived and actual magnitudes for area and volume; the empirical basis for the area and volume penalties in the ranking.
- Mackinlay, Jock (1986). "Automating the design of graphical presentations of relational information." *ACM Transactions on Graphics* 5(2):110–141. Operationalizes the Cleveland-McGill ranking as a ranking function in an automatic-design system; canonical computer-science application.
- Related: `bertin-visual-variables` (the structural catalog of visual encodings, complementary to Cleveland-McGill's empirical ranking); `tufte-data-ink-chartjunk` (the evaluative framework whose recommendations are reinforced by the Cleveland-McGill empirical findings on perceptual accuracy).
