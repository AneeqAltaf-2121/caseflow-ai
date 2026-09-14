variable "name_prefix" {
  description = "Prefix applied to every resource this module creates."
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
