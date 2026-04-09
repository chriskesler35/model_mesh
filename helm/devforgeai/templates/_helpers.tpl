{{/*
Expand the name of the chart.
*/}}
{{- define "devforgeai.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited.
If release name contains chart name it will be used as a full name.
*/}}
{{- define "devforgeai.fullname" -}}
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
{{- define "devforgeai.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "devforgeai.labels" -}}
helm.sh/chart: {{ include "devforgeai.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: devforgeai
{{- end }}

{{/*
Backend labels
*/}}
{{- define "devforgeai.backend.labels" -}}
{{ include "devforgeai.labels" . }}
app.kubernetes.io/name: {{ include "devforgeai.name" . }}-backend
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: backend
app.kubernetes.io/version: {{ .Values.backend.image.tag | default .Chart.AppVersion | quote }}
{{- end }}

{{/*
Backend selector labels
*/}}
{{- define "devforgeai.backend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "devforgeai.name" . }}-backend
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Frontend labels
*/}}
{{- define "devforgeai.frontend.labels" -}}
{{ include "devforgeai.labels" . }}
app.kubernetes.io/name: {{ include "devforgeai.name" . }}-frontend
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: frontend
app.kubernetes.io/version: {{ .Values.frontend.image.tag | default .Chart.AppVersion | quote }}
{{- end }}

{{/*
Frontend selector labels
*/}}
{{- define "devforgeai.frontend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "devforgeai.name" . }}-frontend
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Database URL for backend.
When the postgresql sub-chart is enabled, build the URL from sub-chart values.
Otherwise, expect it in backend.env.DATABASE_URL.
*/}}
{{- define "devforgeai.databaseURL" -}}
{{- if .Values.postgresql.enabled -}}
postgresql+asyncpg://{{ .Values.postgresql.auth.username }}:{{ .Values.postgresql.auth.password }}@{{ include "devforgeai.fullname" . }}-postgresql:5432/{{ .Values.postgresql.auth.database }}
{{- else -}}
{{ .Values.backend.env.DATABASE_URL | default "postgresql+asyncpg://localhost:5432/modelmesh" }}
{{- end -}}
{{- end }}

{{/*
Redis URL for backend.
When the redis sub-chart is enabled, build the URL from sub-chart values.
Otherwise, expect it in backend.env.REDIS_URL.
*/}}
{{- define "devforgeai.redisURL" -}}
{{- if .Values.redis.enabled -}}
redis://:{{ .Values.redis.auth.password }}@{{ include "devforgeai.fullname" . }}-redis-master:6379
{{- else -}}
{{ .Values.backend.env.REDIS_URL | default "redis://localhost:6379" }}
{{- end -}}
{{- end }}

{{/*
Namespace helper -- use Values.namespace if set, otherwise Release.Namespace
*/}}
{{- define "devforgeai.namespace" -}}
{{- default .Release.Namespace .Values.namespace }}
{{- end }}
