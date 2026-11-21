variable "bucket_name" {
  description = "Naam van de bucket. Moet wereldwijd uniek zijn binnen Scaleway (kleine letters, cijfers, streepjes)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "Gebruik 3-63 tekens: kleine letters, cijfers, punten en streepjes."
  }
}

variable "region" {
  description = "Scaleway-regio voor de bucket."
  type        = string
  default     = "nl-ams"

  validation {
    condition     = contains(["nl-ams", "fr-par", "pl-waw"], var.region)
    error_message = "Kies nl-ams, fr-par of pl-waw."
  }
}

variable "project_name" {
  description = "Naam van het aparte Scaleway-project waarin alles komt te staan."
  type        = string
  default     = "boekhouding"
}

variable "deleted_version_retention_days" {
  description = <<-EOT
    Hoe lang overschreven of verwijderde versies onder boekhouding/ (de Litestream-replica)
    bewaard blijven. Beschermt tegen een foute of kwaadwillende delete.
  EOT
  type        = number
  default     = 30
}

variable "archive_glacier_after_days" {
  description = "Na hoeveel dagen jaararchieven (archief/) naar GLACIER gaan. Null = niet verplaatsen. GLACIER bestaat niet in pl-waw."
  type        = number
  default     = 30
  nullable    = true
}

variable "permission_set_names" {
  description = <<-EOT
    Rechten van de Litestream-sleutel, alleen geldig binnen het boekhouding-project.
    Alleen objecten lezen/schrijven/verwijderen: de sleutel kan versioning, lifecycle-regels
    of de bucket zelf niet aanpassen. Werkt dit niet, gebruik dan ["ObjectStorageFullAccess"].
  EOT
  type        = list(string)
  default = [
    "ObjectStorageBucketsRead",
    "ObjectStorageObjectsRead",
    "ObjectStorageObjectsWrite",
    "ObjectStorageObjectsDelete",
  ]
}
