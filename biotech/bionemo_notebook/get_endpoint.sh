#!/bin/bash
RELEASE_ID="applicationrelease-e01sqbfg3vjsxbdyet"
ENTRY_ID=$(npc marketplace inner console release get-release-by-id --release-id $RELEASE_ID | yq '.release.entries[0].id')

OPERATION=$(npc marketplace inner console release create-access --release-id $RELEASE_ID --entry-id $ENTRY_ID)

npc marketplace inner console release get-release-by-id --release-id $RELEASE_ID | yq '.release.entries[0].access.endpoint'
