---
lens_id: bertin-visual-variables
name: Bertin Visual Variables
lens_type: catalog
applicability: [information-density]
foundational: true
source: "Bertin, Jacques (1967/1983). Sémiologie graphique: Les diagrammes, les réseaux, les cartes. Mouton-Gauthier-Villars (English translation: Semiology of Graphics: Diagrams, Networks, Maps, University of Wisconsin Press, 1983; reprint ESRI Press, 2010)."
date created: 2026-05-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - catalog
  - visualization
  - information-design
  - perception
---

# Bertin Visual Variables

## Trigger

Invoked from within `information-density` (T19) when that mode needs the canonical catalog of the seven elementary visual variables — the irreducible primitives by which marks on a graphic encode information — and the four perceptual properties (selective, associative, ordered, quantitative) that determine which variable is appropriate for which kind of data dimension. The host mode supplies a graphic (chart, map, diagram, infographic) and the data dimensions it is encoding (categorical/qualitative, ordinal, quantitative, with magnitude); the lens supplies the seven-variable catalog plus the property tabulation so the analyst can name precisely which variable each data dimension is being encoded into, audit whether the encoding choice matches the dimension's properties, and recommend re-encodings where mismatches are degrading legibility.

## Core Structure

A graphic mark — the smallest meaningful visual unit on a graphic (a dot, a line segment, a bar, a region) — varies along seven dimensions, the *visual variables* (Bertin 1967, traditionally rendered as eight in some translations by separating "value" and "color hue" — the seven-variable convention is followed here, treating value and color hue as distinct variables and consolidating color-related dimensions there). The catalog and its properties are the irreducible vocabulary by which any analytical graphic can be decomposed and evaluated. Each variable is presented with: definition (what the variable is), the four perceptual properties (selective, associative, ordered, quantitative), and an example application that makes the property profile concrete.

### Property definitions

- **Selective.** Can the variable be used to *highlight* a subset — to make a category instantly findable across the graphic? A selective variable lets the eye filter for "all the marks with property X" without sequential scanning.
- **Associative.** Can the variable be used to *group* marks that share the variable's value into a perceived family? An associative variable lets disparate marks read as belonging together when they share a value.
- **Ordered.** Can the variable's values be perceived as having a natural rank (low to high, dim to bright, small to large)? An ordered variable lets the eye read sequence without arbitrary convention.
- **Quantitative.** Can the variable's values be perceived as carrying numeric magnitude (twice as much, half as much, three units more)? A quantitative variable lets the eye estimate ratios and differences, not merely rank.

A variable's properties determine which data-dimension types it can faithfully encode. Quantitative data (numeric magnitudes) demand a quantitative variable; ordinal data (ranked categories) demand an ordered variable; nominal data (unordered categories) need only selective and associative properties. Mismatching variable to dimension produces graphics that the viewer either misreads (quantitative claims encoded in non-quantitative variables) or finds illegible (selective tasks attempted with non-selective variables).

### The Seven Visual Variables

1. **Position.** The location of a mark on the graphic plane (typically along the x or y axis). *Properties:* selective ✓, associative ✓, ordered ✓, quantitative ✓ (the only variable that is fully quantitative). Position is the strongest variable on every property; it is the default for the most important data dimension. Position-on-a-common-scale is the most accurate visual encoding (Cleveland-McGill rank 1). *Example:* the y-axis position of a point in a scatterplot encoding a continuous response variable.

2. **Size.** The dimension of a mark (length, area, or volume). *Properties:* selective ✓, associative limited (large marks read as a group, but small marks are not as cohesive), ordered ✓, quantitative limited (length is more accurately read as quantitative than area; area is more accurately read than volume; the perceptual penalty grows with dimensionality). *Example:* the radius of a bubble in a bubble chart encoding population. Limitation: viewers systematically underestimate area and volume differences; for accurate quantitative encoding, prefer length.

3. **Shape.** The form of the mark (circle, square, triangle, cross, glyph). *Properties:* selective ✓ (a triangle stands out among circles), associative limited (shapes group, but the grouping is weaker than position or color), not ordered, not quantitative. *Example:* shape of a marker in a scatterplot distinguishing categorical groups (e.g., circles for control, triangles for treatment). Use for nominal categories; never for ordinal or quantitative data.

4. **Value.** The lightness or darkness of a mark, holding hue constant (also called *tone* or *brightness*). *Properties:* selective ✓ (a dark mark stands out among light), associative ✓, ordered ✓ (dark to light is perceived as a natural sequence), quantitative limited (value differences are read as ordinal, but viewers cannot accurately compare magnitudes — "twice as dark" has no precise reading). *Example:* sequential color schemes in choropleth maps where lightness encodes magnitude. Use for ordinal or weakly-quantitative data.

5. **Color (hue).** The chromatic dimension (red, blue, green, etc.), holding value constant. *Properties:* selective ✓ (a red mark is instantly findable among blue), associative ✓ (marks of the same hue read as a family), not ordered (no natural rank among hues; sequential hue schemes work only by also varying value), not quantitative. *Example:* hue of regions in a categorical choropleth (climate zone, political affiliation, soil type). Use for nominal categories; for ordinal or quantitative data, use value (lightness) instead, or a perceptually-uniform colormap that varies value as well as hue.

6. **Orientation.** The angle of a mark or its principal axis (vertical, horizontal, 30°, 45°). *Properties:* selective ✓ (a vertical line stands out among horizontal), associative limited, ordered limited (in some contexts — e.g., vector fields where direction is the data), not quantitative. *Example:* orientation of arrows on a vector field map encoding wind direction; orientation of slope lines in a small-multiples sparkline grid. Use sparingly; orientation is weaker than position, value, or color for most tasks.

7. **Texture.** The grain, density, or pattern of a mark's fill (cross-hatching density, dot density, stripe spacing). *Properties:* selective ✓, associative ✓, ordered ✓ (denser textures read as "more"), quantitative limited (similar to value: ordinal but not precisely numeric). *Example:* texture-pattern fills in black-and-white printed maps where color is unavailable. Often a compromise variable for media constraints; in color-available contexts, value or hue typically outperforms.

### Properties Tabulation

| Variable | Selective | Associative | Ordered | Quantitative |
|---|---|---|---|---|
| Position | ✓ | ✓ | ✓ | ✓ (full) |
| Size | ✓ | limited | ✓ | limited (length > area > volume) |
| Shape | ✓ | limited | ✗ | ✗ |
| Value (lightness) | ✓ | ✓ | ✓ | limited (ordinal) |
| Color (hue) | ✓ | ✓ | ✗ | ✗ |
| Orientation | ✓ | limited | limited | ✗ |
| Texture | ✓ | ✓ | ✓ | limited (ordinal) |

The table is the operational guide. A graphic encoding quantitative magnitude in shape (e.g., bubble shapes that change form by magnitude) is mismatched: shape is not quantitative. A graphic encoding nominal categories in value (lightness) is mismatched: viewers will read the lightness as a rank order that the data do not support. Audit by walking each data dimension through the table and confirming the encoded variable supports the property the dimension demands.

### Variable Combinations and Layering

Most analytical graphics encode several data dimensions simultaneously, using different variables for different dimensions. Position-x plus position-y plus size plus hue plus shape encodes five dimensions in a single point mark — the canonical multivariate scatterplot. Combinations work best when the strongest variable (position) carries the most important dimension, and weaker variables carry secondary dimensions that the viewer can ignore when focused on the primary. When many variables are loaded into a single mark, the graphic approaches its perceptual limits; the viewer can attend to two or three variables fluently, but a five-variable mark requires sequential reading rather than gestalt comprehension.

## Application Steps

1. Receive the graphic and its declared data dimensions from the host mode.
2. For each data dimension, identify which visual variable is encoding it.
3. Classify each data dimension's type (nominal, ordinal, quantitative).
4. Audit the variable-to-dimension match: walk each pair through the properties table; flag mismatches (quantitative dimension in non-quantitative variable; ordinal dimension in non-ordered variable; nominal dimension in ordered variable that suggests false rank).
5. Audit the load: count variables per mark; flag overloaded marks (more than three variables loaded simultaneously) and recommend layering (small multiples) instead.
6. Recommend re-encodings for each mismatch; in each recommendation, name the variable to use and the property the variable supports.
7. Return the per-dimension audit, the load assessment, and the re-encoding recommendations to the host mode.

## Detection Signals

- A graphic encodes multiple data dimensions and the analyst suspects some are mismatched to their visual variables.
- The host mode `information-density` is dispatching and the dispatch invokes this lens.
- A categorical color scheme is being used to encode ordered data; the order is not preserved by hue.
- A bubble chart or shape-size encoding is being used to claim quantitative magnitude; the perceptual penalty is being underestimated.
- A graphic feels "muddled" or hard to read despite individually justifiable design choices; the cause may be variable overload or mismatch.
- A black-and-white reproduction is being prepared and the analyst needs to know which variables remain available when color is removed.
- A new visualization is being designed and the analyst needs the catalog to choose encodings systematically.

## Critical Questions

- Has each data dimension been classified as nominal, ordinal, or quantitative before encoding choices are evaluated?
- Does the encoded variable actually support the property the dimension demands? Walk each pair through the table.
- Has the load on each mark been audited? Multivariate marks beyond three or four variables typically degrade gestalt comprehension; the design should consider small multiples.
- When color (hue) is being used for ordered data, has the analyst confirmed the colormap is perceptually uniform (varies value alongside hue), or is hue alone being asked to carry the order?
- When size is being used quantitatively, has the analyst chosen length over area over volume, in line with the perceptual-accuracy gradient?
- Is the analyst confusing selective (highlighting a subset) with quantitative (encoding magnitude)? Both are useful properties, but they are not interchangeable.
- Has the analyst considered the medium constraint? In black-and-white print, color (hue) is unavailable; texture and value carry the load that color would have carried.

## Common Failure Modes

- **Quantitative-in-non-quantitative-variable** — encoding numeric magnitude in shape, hue, or orientation. Detection: the legend asks the viewer to read shapes or colors as having numeric values. Correction: re-encode to position, length, or (with explicit accuracy caveat) area; use shape and hue for nominal categories only.
- **Ordered-in-non-ordered-variable** — encoding ranked categories in shape or hue. Detection: the legend lists categories in order, but the visual encoding gives no perceptual cue that they are ordered. Correction: re-encode to value (lightness), size, or position; reserve shape for unordered nominal data.
- **Nominal-in-ordered-variable** — encoding unordered categories in value or size such that the viewer reads false rank. Detection: viewers ask which category is "higher" or "more" when the data have no such order. Correction: re-encode to hue or shape; reserve value, size, and position for data with a real order.
- **Multivariate overload** — loading more than three or four variables onto a single mark. Detection: the legend requires extensive study and the marks resist gestalt comprehension. Correction: distribute dimensions across small multiples or layered views; preserve gestalt comprehension within each panel.
- **Hue-as-ordered** — using a categorical color scheme (rainbow palette, qualitative palette) to encode ordered or quantitative data. Detection: the colormap has no perceptual progression in lightness; viewers cannot tell which color is "highest." Correction: switch to a perceptually-uniform sequential colormap (viridis, magma, gray-scale variants) or use value (lightness) directly.
- **Area-as-fully-quantitative** — assuming bubble-area encodings communicate magnitudes accurately. Detection: viewers consistently underestimate large-bubble values relative to the data. Correction: prefer length encodings (bars) for accurate quantitative reading; if area is required (e.g., on a map), include a clear area-to-magnitude legend and accept the perceptual penalty.
- **Texture-as-default** — using texture in color-available contexts where value or hue would outperform. Detection: the graphic uses cross-hatching or stippling when color is freely available. Correction: reserve texture for media without color or for niche cases where texture's particular character (e.g., contour shading) is needed; default to value or hue.

## Source Citations

- Bertin, Jacques (1967). *Sémiologie graphique: Les diagrammes, les réseaux, les cartes*. Mouton-Gauthier-Villars. The foundational French original; the canonical statement of the visual-variables framework.
- Bertin, Jacques (1983). *Semiology of Graphics: Diagrams, Networks, Maps* (W. J. Berg, trans.). University of Wisconsin Press. The standard English translation; reissued by ESRI Press (2010) with new introduction.
- Bertin, Jacques (1981). *Graphics and Graphic Information Processing* (W. J. Berg & P. Scott, trans.). Walter de Gruyter. Bertin's accessible exposition of the framework with worked examples.
- MacEachren, Alan M. (1995). *How Maps Work: Representation, Visualization, and Design*. Guilford Press. Cartographic extension of the Bertin framework with cognitive-perceptual research integrated.
- Munzner, Tamara (2014). *Visualization Analysis and Design*. CRC Press. Modern visualization-design textbook that builds on Bertin's framework with empirical updates and computational vocabulary.
- Wilkinson, Leland (2005). *The Grammar of Graphics* (2nd edition). Springer. The framework underlying ggplot2 and modern grammar-of-graphics tools; makes Bertin's encoding choices explicit as language constructs.
- Related: `tufte-data-ink-chartjunk` (the evaluative framework that complements Bertin's encoding catalog); `cleveland-mcgill-perceptual-tasks` (the empirical ranking of perceptual accuracy by encoding type, which refines Bertin's quantitative-property ratings with experimental evidence).
