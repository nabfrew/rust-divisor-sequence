# Cycle values vs m

- plot of cylcle values (most common, min, max) shows that there are certain sets of values share by the manny cycles.
  - e.g. between m=285 and m=325, 17 m-values have cycles with 3 distinct values min 2622 max 2630. 
  - Then there are up to m=597 many values that visually on the plot looks like a continuation of the same horizontall line, but have subtly different sets o f values. e.g. 4 distinct values in range 2624-2638.
  - These don't all have the same cycle length, so are probably not typically truly identical cycles.
- Ranges of such attractors overlap. 
- There are scatterings of lone points throughout that are not part of any such pattern.
- Some other patterns exist, e.g in the plot of m vs. cycle_min there is are linear increasing patterns 
  - typically leading up to the stable attractors
  - In these cases the range between cycle_min and cycle_max tends to be higher.
- Generally cycle_max-cyclemin is small. ~10-20 range. The are som outliers between 601 and 751, e.g. for 601 it is 6551. Some confluence of highly composite coming in and out of the window in that range?

- The cycle values generally seems to exist in some range centred around m*ln(m) - which is expected as ln(m) is the average nr of prime divisors of m.
  - This 'permitted range' increases as m increases. defining the bounds would be interesting. A trivial lower bound is m, as that would be all primes, but the real lower bound seems to be higher.

# Values of m with cycle length 1 are interesting.
These values of m (>1) have a cycle length of 1

m|repeat_after|max_value|Prime|cycle_length|cycle_value|cycle_value/(8*m)|m*ln(m)
---|-----------|---------|-----|-------------|---------| ---|-------
127|18958|1322|TRUE|1|1016|1|615.2
167|34532|2038|TRUE|1|1336|1|854.7
211|979783|2650|TRUE|1|1688|1|1129.2
613|14143541|8258|TRUE|1|4904|1|3934.4
733|52900083|10216|TRUE|1|5864|1|4835.7
1291|4180785143|18902|TRUE|1|10328|1|9247.6

# State space
For the purposes of cycle detection, it is perhaps interesting when the sequence gets locked in to a set of values within that all generate one of the values already within the window. This is a point of no return where it cannot escape finding a cycle eventually, but might meander for many steps.

# Other initialisations
An interesting angle might be instead of 1, do a sampling of randomised initialisations (perhaps distribution centred on m*lm(m) to skip the 'build-up phase'). This will find attractors and how 'powerful' they are. Hypothesis - every prime m has a cycle of length 1, some might just get stuck in a different loop before they find that one.