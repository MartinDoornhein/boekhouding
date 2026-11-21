output "bucket" {
  value = scaleway_object_bucket.data.name
}

output "region" {
  value = scaleway_object_bucket.data.region
}

output "endpoint" {
  value = "https://s3.${scaleway_object_bucket.data.region}.scw.cloud"
}

output "project_id" {
  value = scaleway_account_project.boekhouding.id
}

# Gebruik: terraform output -raw env_file > ../../.env
output "env_file" {
  sensitive = true
  value     = <<-EOT
    BOEKHOUDING_S3_BUCKET=${scaleway_object_bucket.data.name}
    BOEKHOUDING_S3_REGION=${scaleway_object_bucket.data.region}
    LITESTREAM_ACCESS_KEY_ID=${scaleway_iam_api_key.litestream.access_key}
    LITESTREAM_SECRET_ACCESS_KEY=${scaleway_iam_api_key.litestream.secret_key}
  EOT
}
