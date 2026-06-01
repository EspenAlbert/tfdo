output "pet_id" {
  value = random_pet.server.id
}

output "token" {
  value = random_string.token.result
}

output "stack" {
  value = "networking"
}
