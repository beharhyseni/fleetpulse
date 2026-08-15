output "public_ip" {
  value = aws_eip.node.public_ip
}

output "ssh" {
  value = "ssh ubuntu@${aws_eip.node.public_ip}"
}

output "app_url" {
  value = "http://app.${aws_eip.node.public_ip}.nip.io"
}
