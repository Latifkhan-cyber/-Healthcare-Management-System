from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import User

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'phone', 'first_name', 'last_name', 'gender', 'date_of_birth', 'address')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' form-control').strip()
            if field_name == 'date_of_birth':
                field.widget.attrs['type'] = 'date'
            placeholders = {
                'username': 'Choose a username',
                'email': 'your@email.com',
                'phone': 'e.g., 0300-1234567',
                'first_name': 'First name',
                'last_name': 'Last name',
                'address': 'Your address (optional)',
            }
            if field_name in placeholders:
                field.widget.attrs['placeholder'] = placeholders[field_name]


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'phone', 'role')


class StaffCreationForm(UserCreationForm):
    """Form for admin to create staff accounts (Receptionist / Doctor)."""
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'phone', 'first_name', 'last_name',
                  'gender', 'role', 'specialization', 'consultation_fee')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit role choices to staff roles only
        self.fields['role'].choices = [
            ('DOCTOR', 'Doctor'),
            ('RECEPTIONIST', 'Receptionist'),
        ]
        for field_name, field in self.fields.items():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' form-control').strip()
            placeholders = {
                'username': 'Choose a username',
                'email': 'staff@clinic.com',
                'phone': 'e.g., 0300-1234567',
                'first_name': 'First name',
                'last_name': 'Last name',
                'specialization': 'e.g., Gynecology, Pediatrics',
                'consultation_fee': '500.00',
            }
            if field_name in placeholders:
                field.widget.attrs['placeholder'] = placeholders[field_name]
        # Make specialization and consultation_fee only show for Doctor
        self.fields['specialization'].required = False
        self.fields['consultation_fee'].required = False
