{{/* Generate the list of custom plugin monitors based on enabled flags */}}
{{- define "npd.customPluginMonitors" -}}
{{- $monitors := list -}}
{{- if .Values.gpu_count.enabled -}}
  {{- $monitors = append $monitors "/config/custom-plugin-gpu-count.json" -}}
{{- end -}}
{{- if .Values.gpu_xid.enabled -}}
  {{- $monitors = append $monitors "/config/custom-plugin-gpu-xid.json" -}}
{{- end -}}
{{- if .Values.gpu_ecc.enabled -}}
  {{- $monitors = append $monitors "/config/custom-plugin-gpu-ecc.json" -}}
{{- end -}}
{{- if .Values.gpu_nvlink.enabled -}}
  {{- $monitors = append $monitors "/config/custom-plugin-gpu-nvlink.json" -}}
{{- end -}}
{{- if .Values.gpu_ib.enabled -}}
  {{- $monitors = append $monitors "/config/custom-plugin-ib.json" -}}
{{- end -}}
{{- if .Values.gpu_throttle.enabled -}}
  {{- $monitors = append $monitors "/config/custom-plugin-gpu-throttle.json" -}}
{{- end -}}
{{- join "," $monitors -}}
{{- end -}}

{{/*
Build system log monitors string based on enabled components
*/}}
{{- define "npd.systemLogMonitors" -}}
{{- $monitors := list -}}
{{- if .Values.kernel.enabled -}}
{{- $monitors = append $monitors "/config/kernel-monitor.json" -}}
{{- end -}}
{{- if .Values.docker.enabled -}}
{{- $monitors = append $monitors "/config/docker-monitor.json" -}}
{{- end -}}
{{- join "," $monitors -}}
{{- end -}} 