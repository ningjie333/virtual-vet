from bioflow.core.validate_template import validate_template

t = {
    "template_version": "2.0",
    "resolved_parameters": {"total_blood_volume_ml": 5000},
    "beds": [{"name": "brain", "R": 1.0, "C": 2.0, "unstressed_volume_ml": 200}]
}

print(validate_template(t))
