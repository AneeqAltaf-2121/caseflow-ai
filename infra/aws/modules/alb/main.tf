# Phase 50: internet-facing ALB in front of the api and web ECS
# services. Path-based routing sends the api's actual top-level route
# prefixes to the api target group and everything else to web — the
# same split a custom domain's reverse proxy would make, just expressed
# as one ALB rule instead of two DNS names, since no domain/ACM
# certificate exists in this IaC-only scope. HTTPS would be the next
# thing added once a real domain is available (ACM cert + a redirect
# from an HTTP listener); until then this is deliberately HTTP-only on
# port 80.
#
# (Phase 59 correction: this originally routed a single "/api/*"
# pattern, which doesn't match anything — apps/api's routes have no
# "/api" prefix at all (see app/api/router.py: `api_router =
# APIRouter()`, no prefix argument). The api's real top-level paths are
# /health, /ready, /auth/*, and /projects/* — listed explicitly below.)

resource "aws_lb" "this" {
  name               = "${var.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.security_group_id]
  subnets            = var.public_subnet_ids

  tags = var.tags
}

# --- api target group -----------------------------------------------
# Health-checked against /ready (not /health): the ALB should only
# route traffic to a task once it can actually serve requests (DB and
# Redis reachable), not merely once the process is up. /health is used
# instead for the container-level Docker HEALTHCHECK (Phase 39) — a
# looser liveness check appropriate for restart decisions.

resource "aws_lb_target_group" "api" {
  name        = "${var.name_prefix}-api"
  port        = var.api_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip" # required for awsvpc-networked Fargate tasks

  health_check {
    path                = "/ready"
    matcher             = "200"
    interval            = var.health_check_interval
    healthy_threshold   = var.healthy_threshold
    unhealthy_threshold = var.unhealthy_threshold
  }

  tags = var.tags
}

# --- web target group ---------------------------------------------------

resource "aws_lb_target_group" "web" {
  name        = "${var.name_prefix}-web"
  port        = var.web_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/"
    matcher             = "200"
    interval            = var.health_check_interval
    healthy_threshold   = var.healthy_threshold
    unhealthy_threshold = var.unhealthy_threshold
  }

  tags = var.tags
}

# --- listener + routing --------------------------------------------------

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }

  tags = var.tags
}

resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/health", "/ready", "/auth/*", "/projects/*"]
    }
  }
}
