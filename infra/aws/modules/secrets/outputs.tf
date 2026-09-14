output "oauth_client_secret_arn" {
  value = aws_secretsmanager_secret.oauth_client_secret.arn
}

output "anthropic_api_key_arn" {
  value = aws_secretsmanager_secret.anthropic_api_key.arn
}

output "openai_api_key_arn" {
  value = aws_secretsmanager_secret.openai_api_key.arn
}

output "jwt_secret_key_arn" {
  value = aws_secretsmanager_secret.jwt_secret_key.arn
}
