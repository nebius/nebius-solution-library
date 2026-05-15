# DevPods Follow-Up

Nebius' public Serverless AI product page describes DevPods as interactive development environments with tools such as Jupyter and VS Code. The same page marks DevPods as "Coming soon", and the current Serverless AI documentation tree does not expose a DevPods quickstart or CLI workflow.

Do not merge a runnable DevPods example into the solution library until public documentation provides:

- the CLI command or API surface for creating a DevPod;
- supported CPU/GPU platforms and presets;
- network and storage options;
- authentication and access behavior for Jupyter or VS Code;
- lifecycle and cleanup commands;
- pricing and quota behavior.

## Proposed artifact once public docs are available

```text
serverless-ai/devpods/
  README.md
  run.sh
  stop.sh
  delete.sh
```

The artifact should mirror the Jobs and Endpoints examples in this directory: read shared defaults from `environment.sh`, create one minimal resource, print exact validation commands, and print cleanup commands.
