variable "name_prefix" {
  description = "Prefix applied to every resource this module creates."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zone_count" {
  description = "Number of availability zones to spread public/private subnets across."
  type        = number
  default     = 2

  validation {
    condition     = var.availability_zone_count >= 2
    error_message = "At least 2 availability zones are needed for the ALB and RDS to be genuinely multi-AZ capable."
  }
}

variable "single_nat_gateway" {
  description = <<-EOT
    One shared NAT gateway for every private subnet (cheaper, a single
    point of failure for outbound internet access) instead of one per
    AZ (resilient, ~3x the NAT gateway cost). true is the appropriate
    default for a dev environment; a production environment would set
    this false.
  EOT
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags merged onto every resource this module creates."
  type        = map(string)
  default     = {}
}
