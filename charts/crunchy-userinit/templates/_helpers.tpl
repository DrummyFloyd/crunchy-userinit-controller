{{/*
Expand the name of the chart.
*/}}
{{- define "crunchy-userinit.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "crunchy-userinit.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "crunchy-userinit.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "crunchy-userinit.labels" -}}
helm.sh/chart: {{ include "crunchy-userinit.chart" . }}
{{ include "crunchy-userinit.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "crunchy-userinit.selectorLabels" -}}
app.kubernetes.io/name: {{ include "crunchy-userinit.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "crunchy-userinit.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "crunchy-userinit.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Validate if a namespace name contains Kopf patterns that require cluster RBAC
Kopf supports: *, ?, ! (negation), , (multiple patterns)
*/}}
{{- define "crunchy-userinit.isKopfPattern" -}}
{{- $name := . -}}
{{- $isPattern := false -}}
{{- if or (contains "*" $name) (contains "?" $name) (contains "!" $name) (contains "," $name) -}}
  {{- $isPattern = true -}}
{{- end -}}
{{- $isPattern -}}
{{- end -}}

{{- define "crunchy-userinit.needsClusterRBAC" -}}
{{- $needsCluster := false -}}
{{- if eq .Values.watch.mode "all" -}}
  {{- $needsCluster = true -}}
{{- else if eq .Values.watch.mode "list" -}}
  {{- range .Values.watch.namespaces -}}
    {{- $isPattern := include "crunchy-userinit.isKopfPattern" . -}}
    {{- if eq $isPattern "true" -}}
      {{- $needsCluster = true -}}
    {{- end -}}
  {{- end -}}
{{- end -}}
{{- if .Values.rbac.forceCluster -}}
  {{- $needsCluster = true -}}
{{- end -}}
{{- if $needsCluster -}}
true
{{- else -}}
false
{{- end -}}
{{- end -}}

{{/*
Validate watch configuration
*/}}
{{- define "crunchy-userinit.validateWatchConfig" -}}
{{- if not (has .Values.watch.mode (list "current" "all" "list")) -}}
  {{- fail "watch.mode must be one of: current, all, list" -}}
{{- end -}}

{{- if and (eq .Values.watch.mode "list") (not .Values.watch.namespaces) -}}
  {{- fail "watch.namespaces cannot be empty when watch.mode is 'list'" -}}
{{- end -}}

{{- if and (ne .Values.watch.mode "list") .Values.watch.namespaces -}}
  {{- fail "watch.namespaces should only be set when watch.mode is 'list'" -}}
{{- end -}}
{{- end -}}

{{/*
Generate deployment args
*/}}
{{- define "crunchy-userinit.deploymentArgs" -}}
- --log-format={{ .Values.log.format }}
{{- if .Values.log.debug }}
- --debug
{{- end }}
{{- if .Values.livenessProbe.enabled }}
- --liveness=http://0.0.0.0:8080/healthz
{{- end }}
{{- if eq .Values.watch.mode "all" }}
- --all-namespaces
{{- else if eq .Values.watch.mode "list" }}
{{- range .Values.watch.namespaces }}
- --namespace={{ . }}
{{- end }}
{{- else }}
- --namespace={{ .Release.Namespace }}
{{- end }}
{{- end -}}

{{/*
Generate configuration summary for NOTES.txt
*/}}
{{- define "crunchy-userinit.configSummary" -}}
{{- $clusterRBAC := include "crunchy-userinit.needsClusterRBAC" . -}}

Configuration Summary:
- Watch Mode: {{ .Values.watch.mode }}
{{- if eq .Values.watch.mode "list" }}
- Watched Namespaces: {{ .Values.watch.namespaces | join ", " }}
{{- end }}
- RBAC Type: {{ if eq $clusterRBAC "true" }}Cluster-wide{{ else }}Namespace-scoped{{ end }}
{{- if .Values.rbac.forceCluster }}
- Cluster RBAC: Forced enabled
{{- else if eq $clusterRBAC "true" }}
{{- if eq .Values.watch.mode "all" }}
- Cluster RBAC: Auto-enabled (watching all namespaces)
{{- else }}
- Cluster RBAC: Auto-enabled (Kopf patterns detected)
{{- end }}
{{- end }}
{{- end -}}
