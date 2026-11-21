# Apart project: een uitgelekte sleutel kan alleen bij deze bucket, niet bij de rest van je account.
resource "scaleway_account_project" "boekhouding" {
  name        = var.project_name
  description = "Boekhouding: Litestream-replica en jaararchieven"
}

resource "scaleway_object_bucket" "data" {
  name       = var.bucket_name
  project_id = scaleway_account_project.boekhouding.id
  region     = var.region

  # Versioning: een delete of overschrijving laat de vorige versie staan.
  # Let op: eenmaal aan kan versioning nooit meer helemaal uit.
  versioning {
    enabled = true
  }

  # Litestream-replica: Litestream ruimt zelf op (30 dagen). Wat het verwijdert blijft door
  # versioning nog `deleted_version_retention_days` bestaan als vangnet en verdwijnt daarna.
  lifecycle_rule {
    id                                     = "litestream-oude-versies"
    prefix                                 = "boekhouding/"
    enabled                                = true
    abort_incomplete_multipart_upload_days = 1

    noncurrent_version_expiration {
      noncurrent_days = var.deleted_version_retention_days
    }
  }

  # Jaararchieven (scripts/archive.sh): nooit automatisch verwijderd; na een tijdje naar
  # goedkope GLACIER-opslag. Ook verwijderde versies hiervan blijven bewaard.
  lifecycle_rule {
    id                                     = "archief"
    prefix                                 = "archief/"
    enabled                                = true
    abort_incomplete_multipart_upload_days = 1

    dynamic "transition" {
      for_each = var.archive_glacier_after_days == null || var.region == "pl-waw" ? [] : [1]
      content {
        days          = var.archive_glacier_after_days
        storage_class = "GLACIER"
      }
    }
  }
}

# Aparte applicatie (geen gebruiker) met een sleutel die alleen Object Storage in dit project mag.
resource "scaleway_iam_application" "litestream" {
  name        = "${var.project_name}-litestream"
  description = "Litestream-replicatie en archief-upload voor de boekhouding"
}

resource "scaleway_iam_policy" "litestream" {
  name           = "${var.project_name}-litestream-object-storage"
  description    = "Alleen Object Storage, alleen in het ${var.project_name}-project"
  application_id = scaleway_iam_application.litestream.id

  rule {
    project_ids          = [scaleway_account_project.boekhouding.id]
    permission_set_names = var.permission_set_names
  }
}

resource "scaleway_iam_api_key" "litestream" {
  application_id     = scaleway_iam_application.litestream.id
  default_project_id = scaleway_account_project.boekhouding.id
  description        = "Litestream (boekhouding)"
}
