variable "name_prefix" {
  description = "Prefix applied to every resource this module creates."
  type        = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  description = "Public subnets the internet-facing ALB itself lives in."
  type        = list(string)
}

variable "security_group_id" {
  description = "The networking module's ALB security group (ingress 80/443 from the internet)."
  type        = string
}

variable "api_port" {
  type    = number
  default = 8000
}

variable "web_port" {
  type    = number
  default = 3000
}

variable "health_check_interval" {
  type    = number
  default = 30
}

variable "healthy_threshold" {
  type    = number
  default = 2
}

variable "unhealthy_threshold" {
  type    = number
  default = 3
}

variable "tags" {
  type    = map(string)
  default = {}
}
