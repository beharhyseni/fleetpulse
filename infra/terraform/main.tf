data "aws_ami" "ubuntu_arm" { # newest official Ubuntu 24.04, ARM
  most_recent = true
  owners      = ["099720109477"] # Canonical's publisher ID
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd*/ubuntu-noble-24.04-arm64-server-*"]
  }
}

resource "aws_key_pair" "me" { # your door key, registered with AWS
  key_name   = "fleetpulse"
  public_key = file(pathexpand(var.ssh_public_key_path))
}

resource "aws_security_group" "fleetpulse" { # firewall: deny-all + these doors
  name = "fleetpulse"

  ingress { # SSH — your IP only
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress { # the world may knock on HTTP
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress { # ...and HTTPS
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress { # outbound: everything (image pulls, apt)
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_eip" "node" { # permanent street address — allocated FIRST
  domain = "vpc"            # so the boot script can know it
}

resource "aws_instance" "node" {
  ami                    = data.aws_ami.ubuntu_arm.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.me.key_name
  vpc_security_group_ids = [aws_security_group.fleetpulse.id]

  user_data = templatefile("${path.module}/user_data.sh.tpl", {
    public_ip = aws_eip.node.public_ip # baked into first boot
  })

  root_block_device {
    volume_size = 16
    volume_type = "gp3"
  }

  tags = { Name = "fleetpulse" }
}

resource "aws_eip_association" "node" { # staple the address onto the machine
  instance_id   = aws_instance.node.id
  allocation_id = aws_eip.node.id
}
