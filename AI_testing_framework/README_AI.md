# AI Testing Framework (Interview Edition)

This folder contains an isolated AI regression-impact pipeline.
It is designed to **not change default behavior** of existing test scripts.

## Files

- `ai_pipeline_entry.py`: unified pipeline entrypoint
- `impact_engine.py`: core impact analysis engine
- `llm_provider.py`: pluggable fallback providers (`noop`, `keyword_vote`)
- `validate_mapping.py`: config validator
- `selfcheck_ai_pipeline.py`: tiny self-check runner
- `analyze_impact.py`: compatibility CLI wrapper
- `module_mapping.yaml`: module mapping config
- `impact_analysis_result.json`: pipeline output (generated)

## Design Principles

1. Non-intrusive: existing test scripts run as before.
2. Explainable: output includes decision trace and evidence.
3. Safe fallback: unmatched changes degrade to full regression command.

## Quick Start

Run mapping validation:

```powershell
python .\AI_testing_framework\validate_mapping.py
```

Run backend trigger analysis:

```powershell
python .\AI_testing_framework\ai_pipeline_entry.py --trigger backend --diff
```

Run algorithm trigger analysis:

```powershell
python .\AI_testing_framework\ai_pipeline_entry.py --trigger algorithm --service "切图服务"
```

Run self-check:

```powershell
python .\AI_testing_framework\selfcheck_ai_pipeline.py
```

## Output

Default output path:

- `AI_testing_framework/impact_analysis_result.json`

Schema:

- `trigger`: backend / algorithm
- `affected_modules`: selected modules or algorithm mapping result
- `pytest_command`: generated command for pipeline execution
- `trace`: decision path and evidence

## Notes

- No external LLM API is required by default.
- For interview demos, `keyword_vote` provider can simulate fallback behavior.

