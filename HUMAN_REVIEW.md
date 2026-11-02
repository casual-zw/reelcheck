# Development-label review

These are AI-drafted development labels, not independently validated benchmark truth. Review each against only the supplied passages. The same source or claim variants must remain in one split. There are 16 cases across four source families.

For each case, mark agreement or record a corrected label and reason. Missing evidence is insufficient even if you know the real-world answer. Do not tune against a future final test set.

## dev_01 — qualified_support

**Claim:** Water's density is roughly 1 gram per milliliter, and it changes with temperature and dissolved substances.

**Draft label:** supported

**D1** ([source](https://www.usgs.gov/water-science-school/science/water-density))

> The density of water is roughly 1 gram per milliliter but, this changes with temperature or if there are substances dissolved in it.

**D2** ([source](https://www.usgs.gov/water-science-school/science/water-density))

> Ice is less dense than liquid water which is why your ice cubes float in your glass.

- [ ] Label and evidence independently checked
- Reviewer / corrected label / notes:

## dev_02 — exception

**Claim:** Heavy-water ice sinks in normal water.

**Draft label:** supported

**D2** ([source](https://www.usgs.gov/water-science-school/science/water-density))

> Ice is less dense than liquid water which is why your ice cubes float in your glass.

**D3** ([source](https://www.usgs.gov/water-science-school/science/water-density))

> Heavy water is indeed heavier than normal water (which contains a tiny amount of heavy water molecules naturally), and heavy-water ice will sink in normal water.

- [ ] Label and evidence independently checked
- Reviewer / corrected label / notes:

## dev_03 — overbroad_scope

**Claim:** Every kind of ice floats in normal water, including heavy-water ice.

**Draft label:** contradicted

**D2** ([source](https://www.usgs.gov/water-science-school/science/water-density))

> Ice is less dense than liquid water which is why your ice cubes float in your glass.

**D3** ([source](https://www.usgs.gov/water-science-school/science/water-density))

> Heavy water is indeed heavier than normal water (which contains a tiny amount of heavy water molecules naturally), and heavy-water ice will sink in normal water.

- [ ] Label and evidence independently checked
- Reviewer / corrected label / notes:

## dev_04 — withheld_decisive_evidence

**Claim:** Heavy-water ice sinks in normal water.

**Draft label:** insufficient / missing_evidence

**D1** ([source](https://www.usgs.gov/water-science-school/science/water-density))

> The density of water is roughly 1 gram per milliliter but, this changes with temperature or if there are substances dissolved in it.

- [ ] Label and evidence independently checked
- Reviewer / corrected label / notes:

## dev_05 — normal

**Claim:** Evaporation changes liquid water into water vapor.

**Draft label:** supported

**E1** ([source](https://www.usgs.gov/water-science-school/science/evaporation-and-water-cycle))

> Evaporation is the process that changes liquid water to gaseous water (water vapor).

**E3** ([source](https://www.usgs.gov/water-science-school/science/evaporation-and-water-cycle))

> Condensation is the process of water vapor turning back into liquid water.

- [ ] Label and evidence independently checked
- Reviewer / corrected label / notes:

## dev_06 — condition

**Claim:** Water cannot evaporate at its freezing point; evaporation only happens at its boiling point.

**Draft label:** contradicted

**E1** ([source](https://www.usgs.gov/water-science-school/science/evaporation-and-water-cycle))

> Evaporation is the process that changes liquid water to gaseous water (water vapor).

**E2** ([source](https://www.usgs.gov/water-science-school/science/evaporation-and-water-cycle))

> Water easily evaporates at its boiling point (212° F, 100° C) but evaporates much more slowly at its freezing point because of the heat energy required to evaporate the water.

- [ ] Label and evidence independently checked
- Reviewer / corrected label / notes:

## dev_07 — direction

**Claim:** Condensation turns liquid water into water vapor.

**Draft label:** contradicted

**E1** ([source](https://www.usgs.gov/water-science-school/science/evaporation-and-water-cycle))

> Evaporation is the process that changes liquid water to gaseous water (water vapor).

**E3** ([source](https://www.usgs.gov/water-science-school/science/evaporation-and-water-cycle))

> Condensation is the process of water vapor turning back into liquid water.

- [ ] Label and evidence independently checked
- Reviewer / corrected label / notes:

## dev_08 — missing_condition_evidence

**Claim:** Pure water boils at exactly 100 degrees Celsius at every altitude.

**Draft label:** insufficient / missing_evidence

**E1** ([source](https://www.usgs.gov/water-science-school/science/evaporation-and-water-cycle))

> Evaporation is the process that changes liquid water to gaseous water (water vapor).

**E3** ([source](https://www.usgs.gov/water-science-school/science/evaporation-and-water-cycle))

> Condensation is the process of water vapor turning back into liquid water.

- [ ] Label and evidence independently checked
- Reviewer / corrected label / notes:

## dev_09 — qualified_quantity

**Claim:** The Moon is about 384,400 kilometers from Earth on average.

**Draft label:** supported

**M1** ([source](https://science.nasa.gov/moon/facts/))

> The Moon is an average of 238,855 miles (384,400 kilometers) away.

**M2** ([source](https://science.nasa.gov/moon/facts/))

> The Moon has a very thin and tenuous atmosphere called an exosphere. It is not breathable.

- [ ] Label and evidence independently checked
- Reviewer / corrected label / notes:

## dev_10 — compound_support

**Claim:** The Moon has a thin exosphere that humans cannot breathe.

**Draft label:** supported

**M2** ([source](https://science.nasa.gov/moon/facts/))

> The Moon has a very thin and tenuous atmosphere called an exosphere. It is not breathable.

**M3** ([source](https://science.nasa.gov/moon/facts/))

> The Moon has no rings.

- [ ] Label and evidence independently checked
- Reviewer / corrected label / notes:

## dev_11 — wrong_unit

**Claim:** The Moon's average distance from Earth is 384,400 miles.

**Draft label:** contradicted

**M1** ([source](https://science.nasa.gov/moon/facts/))

> The Moon is an average of 238,855 miles (384,400 kilometers) away.

**M3** ([source](https://science.nasa.gov/moon/facts/))

> The Moon has no rings.

- [ ] Label and evidence independently checked
- Reviewer / corrected label / notes:

## dev_12 — average_vs_specific_date

**Claim:** On January 1, 2030, the Moon will be exactly 384,400 kilometers from Earth.

**Draft label:** insufficient / missing_evidence

**M1** ([source](https://science.nasa.gov/moon/facts/))

> The Moon is an average of 238,855 miles (384,400 kilometers) away.

**M3** ([source](https://science.nasa.gov/moon/facts/))

> The Moon has no rings.

- [ ] Label and evidence independently checked
- Reviewer / corrected label / notes:

## dev_13 — normal_quantity

**Claim:** Raising one kilogram of water by one degree Celsius requires 4,184 joules of heat.

**Draft label:** supported

**H1** ([source](https://www.usgs.gov/special-topic/water-science-school/science/heat-capacity-and-water))

> Water has to absorb 4,184 Joules of heat (1 kilocalorie) for the temperature of one kilogram of water to increase 1°C.

**H2** ([source](https://www.usgs.gov/special-topic/water-science-school/science/heat-capacity-and-water))

> For the sake of comparison, it only takes 385 Joules of heat to raise 1 kilogram of copper 1°C.

- [ ] Label and evidence independently checked
- Reviewer / corrected label / notes:

## dev_14 — wrong_entity_quantity

**Claim:** Raising one kilogram of water by one degree Celsius requires only 385 joules of heat.

**Draft label:** contradicted

**H1** ([source](https://www.usgs.gov/special-topic/water-science-school/science/heat-capacity-and-water))

> Water has to absorb 4,184 Joules of heat (1 kilocalorie) for the temperature of one kilogram of water to increase 1°C.

**H2** ([source](https://www.usgs.gov/special-topic/water-science-school/science/heat-capacity-and-water))

> For the sake of comparison, it only takes 385 Joules of heat to raise 1 kilogram of copper 1°C.

- [ ] Label and evidence independently checked
- Reviewer / corrected label / notes:

## dev_15 — wrong_mass_unit

**Claim:** Raising one gram of water by one degree Celsius requires 4,184 joules of heat.

**Draft label:** contradicted

**H1** ([source](https://www.usgs.gov/special-topic/water-science-school/science/heat-capacity-and-water))

> Water has to absorb 4,184 Joules of heat (1 kilocalorie) for the temperature of one kilogram of water to increase 1°C.

**H2** ([source](https://www.usgs.gov/special-topic/water-science-school/science/heat-capacity-and-water))

> For the sake of comparison, it only takes 385 Joules of heat to raise 1 kilogram of copper 1°C.

- [ ] Label and evidence independently checked
- Reviewer / corrected label / notes:

## dev_16 — general_vs_specific

**Claim:** San Francisco's daily temperature range is exactly five degrees Celsius smaller than Sacramento's.

**Draft label:** insufficient / missing_evidence

**H3** ([source](https://www.usgs.gov/special-topic/water-science-school/science/heat-capacity-and-water))

> Cities near the oceans will tend to have less change and less extreme temperatures than inland cities.

- [ ] Label and evidence independently checked
- Reviewer / corrected label / notes:
