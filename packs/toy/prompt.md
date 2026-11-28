You label short passages. Return only JSON. Copy evidence verbatim from the passage.
=====USER=====
For each dimension, give one label. Dimensions and labels:
- sentiment: negative | neutral | positive
- urgency: low | medium | high
Non-neutral and non-low labels need an evidence quote copied verbatim from the passage; otherwise use the neutral or low label with quote "".
Return {"items":[{"id":"sentiment","label":"...","quote":"..."},{"id":"urgency","label":"...","quote":"..."}]}

<passage>
<<PASSAGE>>
</passage>
