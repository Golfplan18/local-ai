# Reference — Trusted Web Sources

High-provenance web sources Ora consults first when the analytical pipeline needs information not in the vault. Used by the Step 2.5 web-supplement loop and by `orchestrator/tools/web_corroboration.py::classify_web_source` for ranking weight per Reference — Ora YAML Schema §15.

Inclusion criteria: easy access (DDG-indexable), structured content, no paywall on article body, broad or authoritative coverage. Patterns are fnmatch globs over URLs with the `http(s)://` prefix stripped. Patterns live in fenced code blocks; subsections (H3) are for human readability and are flattened by the parser.

Paywall status tested 2026-05-16 via direct HTTP fetch. The trend over the last few years has been aggressive paywall conversion — re-test the list periodically and when adding new domains. Reuters was dropped 2026-05-16 after moving behind a paywall.

A handful of domains (HathiTrust, DPLA, Smithsonian, OECD main) return 403 to plain `curl` due to Cloudflare bot detection. The content itself is free and DDG-indexable, so the snippet-only Step 2.5 path works against them; a future page-fetch v2 will need realistic headers or a different fetch path for these.

## High Provenance

Whitelisted domains (weight 0.7). First-look set for the Step 2.5 web-supplement loop.

### Generalist references

```
en.wikipedia.org/*
simple.wikipedia.org/*
en.wikisource.org/*
plato.stanford.edu/*
iep.utm.edu/*
www.britannica.com/*
```

Wikipedia (English + simple-English) covers most named-entity questions. Wikisource for primary documents (constitutions, treaties, court opinions in text form). The Stanford Encyclopedia of Philosophy is the gold standard for philosophy and conceptual analysis; the Internet Encyclopedia of Philosophy is its peer-reviewed sibling with broader and less narrowly academic coverage. Britannica is freemium — the article body is free, "subscribe to Premium" buttons are upsell CTAs rather than content gates.

### US government — primary-source data

```
www.irs.gov/*
fred.stlouisfed.org/*
www.bls.gov/*
www.bea.gov/*
www.census.gov/*
www.cdc.gov/*
www.nih.gov/*
www.nist.gov/*
www.noaa.gov/*
www.nasa.gov/*
www.usgs.gov/*
www.epa.gov/*
www.federalregister.gov/*
www.law.cornell.edu/*
www.archives.gov/*
www.loc.gov/*
```

FRED (Federal Reserve Bank of St. Louis) and BLS (Bureau of Labor Statistics) for economic indicators and labor statistics; BEA (Bureau of Economic Analysis) covers GDP, trade, and national accounts. IRS for tax forms and published guidance; Census for demographics; CDC and NIH for public health and biomedical; NIST for standards; NOAA for weather and climate; NASA for space and Earth science; USGS for geology and hydrology; EPA for environmental rulemaking and data. Federal Register for federal rulemaking; Cornell LII for federal law text; the National Archives and Library of Congress for historical records.

### International / multilateral

```
www.who.int/*
data.worldbank.org/*
data.oecd.org/*
data.imf.org/*
www.un.org/*
unstats.un.org/*
```

OECD is constrained to the data subdomain — the main `oecd.org` publications site triggers partial paywalls. IMF and UN Statistics for international economic and demographic data.

### General news (free article body, no metering observed 2026-05-16)

```
apnews.com/*
www.npr.org/*
www.bbc.com/news/*
www.pbs.org/newshour/*
www.propublica.org/*
```

Associated Press is the syndication source-of-truth for breaking news; NPR / BBC / PBS for accessible public-interest reporting; ProPublica for investigative work. Reuters dropped 2026-05-16 — moved to paywall.

### Open-access academic

```
arxiv.org/*
www.ncbi.nlm.nih.gov/pmc/*
doaj.org/*
scholar.archive.org/*
www.semanticscholar.org/*
core.ac.uk/*
```

arXiv and PubMed Central are the major primary repositories for preprints and open biomedical literature; DOAJ is the curated index of open-access journals; CORE and Semantic Scholar aggregate across the open-access literature; the Internet Archive's Scholar product mirrors and indexes additional open scholarly content.

### Library / archival

```
www.gutenberg.org/*
archive.org/*
openlibrary.org/*
www.hathitrust.org/*
dp.la/*
www.europeana.eu/*
www.biodiversitylibrary.org/*
```

Project Gutenberg for public-domain texts. The Internet Archive (archive.org) and Open Library for the broader scanned-book corpus. HathiTrust for a major academic-library aggregator (public-domain content fully free, in-copyright is search-only). DPLA aggregates US public libraries, museums, and archives; Europeana the European counterpart. Biodiversity Heritage Library for natural-history sources.

### Open educational resources

```
ocw.mit.edu/*
openstax.org/*
www.khanacademy.org/*
www.si.edu/*
```

MIT OpenCourseWare for course material; OpenStax for open textbooks; Khan Academy for K-12 and early-college math and science; Smithsonian Open Access for museum collections and educational material.

### Survey / polling

```
www.pewresearch.org/*
```

Pew Research is the most-cited free source for US public-opinion and demographic surveys.

## Medium Provenance

Patterns here are classified as "corroborated" (weight 0.3) without needing a corroboration count — useful for sources that are generally reliable but should weigh as one of several voices rather than first-look authority. Empty until we identify second-tier sources worth pre-classifying.

## Page-Specific Overrides

Page-level rules override the section-level classification. Format is `<glob pattern> → <classification>` per line, where classification is one of `whitelisted`, `corroborated`, `single`, or `excluded`. Useful when a generally-trusted domain hosts content that should be downgraded (e.g. user-submitted material on an otherwise-authoritative site) or vice versa. Empty until we hit a real case.

## Excluded

Patterns here get weight 0.0 and are dropped from ranking entirely. Use for sources known to host low-quality, AI-generated, or user-submitted content that should never weight into Ora's analysis. Empty until we see the Step 2.5 loop pulling in low-quality matches that warrant explicit exclusion.
