Tuning log · MD
Copy

# Tuning Log — Prototype
 
## Session 1
 
**Platform:** Python prototype, mouse bowing, keyboard pitch
 
### Findings
 
**Nonlinear term (`np.tanh`) causes self-sustaining feedback.**  
Any `nonlinear > 0` prevented decay when mouse was still. Root cause: tanh near zero amplifies rather than attenuates small signals. Fix: removed nonlinear term entirely from loop filter. Stability restored.
 
**Brightness must stay below 0.5.**  
At `brightness >= 0.5` the loop filter stops attenuating and the delay line runs away. All presets constrained to `brightness < 0.5`.
 
**Bow noise threshold needed.**  
Continuous noise injection at `bow > 0.0` prevented decay even when mouse was still due to residual `bow_intensity` from decay thread timing. Fix: threshold raised to `bow > 0.05`.
 
**DC buildup at certain pitches.**  
Some delay line lengths caused low-frequency resonance accumulation. Fix: per-sample stabilizer `x *= 0.98` inside loop.
 
### Final Prototype Parameters
 
| Preset | decay (δ) | brightness (β) | reverb mix | excite amount |
|--------|-----------|----------------|------------|---------------|
| Staccato | 0.9960 | 0.40 | 0.08 | 0.60 |
| Sustained | 0.9998 | 0.30 | 0.35 | 0.20 |
 
**Bow noise scale:** `±0.06 × v` per sample  
**Bow threshold:** `v > 0.05`  
**Decay thread interval:** 30ms, step `−0.15` per tick  
**Reverb:** single comb filter, delay ~43ms, feedback `α = 0.82`
 
### Notes
 
- Singing bowl / cave / metallic drone presets attempted and abandoned — waveguide model does not support these timbres without modal synthesis, which is a different architecture.
- Two presets (Staccato, Sustained) are sufficient for Phase 1.
- Mouse bowing feels reasonable but SoftPot velocity response will need separate tuning on hardware.
 