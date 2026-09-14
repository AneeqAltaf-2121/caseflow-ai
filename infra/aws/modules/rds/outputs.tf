output "db_instance_id" {
  value = aws_db_instance.this.id
}

output "db_endpoint" {
  description = "Host:port to connect to."
  value       = aws_db_instance.this.endpoint
}

output "db_address" {
  description = "Host only, no port."
  value       = aws_db_instance.this.address
}

output "db_port" {
  value = aws_db_instance.this.port
}

output "db_name" {
  value = aws_db_instance.this.db_name
}

output "master_user_secret_arn" {
  description = "Secrets Manager ARN RDS itself created for the master password — see Phase 51 for how the app reads it."
  value       = aws_db_instance.this.master_user_secret[0].secret_arn
}
