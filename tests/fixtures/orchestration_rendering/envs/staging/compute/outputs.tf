output "port" {
  value = random_integer.port.result
}

output "bucket_id" {
  value = random_id.bucket.hex
}

output "stack" {
  value = "compute"
}
