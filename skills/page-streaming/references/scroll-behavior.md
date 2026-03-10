# Explanation of Scroll Behavior

This document explains the processing flow of the **incremental** scroll in `page_streamer.py`, and the scroll amount per iteration (which defaults to 1 viewport).

---

## 1. The 3 Phases + Repetition Common to All Pages

A single scroll operation in **incremental** mode is unified into the following 3 phases regardless of the page:

1. **Coarse Move (coarse)**  
   `scrollTop += viewportHeight * 0.8` -> Example: **4000px** (when viewport=5000)
2. **Sweep (fine)**  
   `scrollTop = base + y` is incrementally set with `y` ranging from `500` (viewport * 0.1) to `1000` (viewport * 0.2).  
   If a planned position `target_position` is specified, the sweep aborts at the planned position, **adjusting fractions to match exactly**.
3. **Wait**  
   Wait for `SCROLL_WAIT_MS` and DOM settle.

**Repetition**:  
If "the planned position has not been reached yet" and "scrollHeight has expanded," this **returns to 2 (Sweep)**.  
At this time, no coarse move is performed; it only sweeps from the current position to the planned position, again adjusting fractions to match exactly.  
This repeats until the planned position is reached, or the scrollHeight no longer expands.

**Limits for a Single Sweep**:  
The planned position is capped so that it **does not exceed the current scrollHeight**. Because virtual rendering can cause scrollHeight to expand with a delay, it first scrolls to the bottom edge of the currently rendered range, waits to check if scrollHeight expands, and if it does, sweeps again.

**When Unreachable**:  
If it scrolls to the bottom edge, waits, but scrollHeight does not change (it cannot scroll any further), it **aborts with an error without a fallback**.

Through this, even when scrollHeight expands with a delay in dynamic content, the `nextPosition` will **always align with the planned position (`currentPosition` + `viewport`)**, including for the final page.

---

## 2. Scroll Amount per Iteration (1 Viewport)

- **Coarse Move**: `viewportHeight * coarse_ratio` -> 0.8 * 5000 = **4000px**
- **Sweep End**: `base + (viewportHeight * fine_end_ratio)` -> base + 0.2 * 5000 = **base + 1000**

Therefore, the **planned position** is:

- `before + 4000 + 1000 = before + 5000` (when viewport=5000)
- In other words, **the move amount per iteration = viewport * (coarse_ratio + fine_end_ratio) = 1.0 * viewport**.  
  By default, it advances by **exactly 1 viewport**, making the pages contiguous.

`clientHeight` / `viewport_height` refers to "the height currently visible," and "how much to scroll in one go" is determined by **`coarse_ratio` + `fine_end_ratio`** (default 1.0).

---

## 3. Summary

| Item | Description |
|------|------|
| 3 Phases | 1) Coarse move 2) Sweep (exact match with the planned position) 3) Wait. If unreached and scrollHeight increases, return to 2 and repeat. |
| Move Amount per Iteration | Planned position = currentPosition + viewport * (0.8+0.2) = **1.0 * viewport**. Pages are contiguous. |
| The Last Page | Due to the repetition above, even if dynamic content stretches, it sweeps up to the planned position, so `nextPosition` is aligned in viewport increments. |
