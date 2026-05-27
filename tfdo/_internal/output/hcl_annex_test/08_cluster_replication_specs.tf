# module.cluster.mongodbatlas_advanced_cluster.this
# Annex: replication_specs after (sensitive and unknown paths stripped)

resource "mongodbatlas_advanced_cluster" "this" {
  replication_specs = [
    {
      region_configs = [
        {
          analytics_auto_scaling = {
            compute_enabled = false,
            disk_gb_enabled = false,
          },
          auto_scaling           = {
            compute_enabled = false,
            disk_gb_enabled = false,
          },
          electable_specs        = {
            instance_size = "M40",
            node_count    = 3,
          },
          priority               = 7,
          provider_name          = "GCP",
          read_only_specs        = {
            instance_size = "M40",
            node_count    = 0,
          },
          region_name            = "US_EAST_4",
        },
      ],
    },
  ]
}
