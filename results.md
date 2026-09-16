# nyayaos-lite evaluation results

Selected on validation: `tau=0.45`, `delta=0.1`, `val_TSA=0.9840`

Weights: `{'wA': 0.2, 'wT': 0.2, 'wX': 0.2, 'wE': 0.4}`

| method | TSA | ConflictAcc | DelayedRob | NoisyRob | CalibCorr | CalibIncorr |
| --- | --- | --- | --- | --- | --- | --- |
| latest_update_wins | 0.384 | 0.240 | 0.360 | 0.000 | — | — |
| majority_voting | 0.472 | 0.720 | 0.000 | 0.320 | — | — |
| fixed_source_authority | 0.840 | 0.520 | 1.000 | 0.680 | — | — |
| CAMS | 0.984 | 0.920 | 1.000 | 1.000 | 0.777 | 0.760 |
| CAMS_ablate_A | 0.672 | 0.000 | 1.000 | 0.680 | 0.836 | 0.684 |
| CAMS_ablate_T | 0.968 | 1.000 | 0.840 | 1.000 | 0.771 | 0.825 |
| CAMS_ablate_X | 0.888 | 0.440 | 1.000 | 1.000 | 0.824 | 0.750 |
| CAMS_ablate_E | 0.568 | 0.160 | 1.000 | 0.000 | 0.819 | 0.652 |
