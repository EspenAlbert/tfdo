# module.gcp.module.log_integration[0].google_storage_bucket.atlas[0]
# Annex: lifecycle_rule after (sensitive and unknown paths stripped)

resource "google_storage_bucket" "atlas" {
  lifecycle_rule {
    action {
      storage_class = ""
      type          = "Delete"
    }

    condition {
      age                    = 90
      created_before         = ""
      custom_time_before     = ""
      noncurrent_time_before = ""
    }
  }
}
