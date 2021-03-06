from flask import abort, flash, redirect, render_template, url_for, request
from flask_login import current_user, login_required
from flask_rq import get_queue
from sqlalchemy.exc import IntegrityError
from .forms import (ChangeAccountTypeForm, ChangeUserEmailForm, InviteUserForm,
                    NewUserForm, AddTagForm, EditTagForm, DeleteTagForm)
from . import admin
from .. import db
from ..decorators import admin_required
from ..email import send_email
from ..models import Role, User, EditableHTML, Tag, TagType, Organization
import re

@admin.route('/')
@login_required
@admin_required
def index():
    """Admin dashboard page."""
    return render_template('admin/index.html')


@admin.route('/new-user', methods=['GET', 'POST'])
@login_required
@admin_required
def new_user():
    """Create a new user."""
    form = NewUserForm()
    if form.validate_on_submit():
        if form.role.data.name == 'Administrator':
            approved_val = True
        else:
            approved_val = False
        user = User(
            role=form.role.data,
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            email=form.email.data,
            approved=approved_val,
            password=form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('User {} successfully created'.format(user.full_name()),
              'form-success')
    return render_template('admin/new_user.html', form=form)


@admin.route('/invite-user', methods=['GET', 'POST'])
@login_required
@admin_required
def invite_user():
    """Invites a new user to create an account and set their own password."""
    form = InviteUserForm()
    if form.validate_on_submit():
        if form.role.data.name == 'Administrator':
            approved_val = True
        else:
            approved_val = False
        user = User(
            role=form.role.data,
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            approved=approved_val,
            email=form.email.data)
        db.session.add(user)
        db.session.commit()
        token = user.generate_confirmation_token()
        invite_link = url_for(
            'account.join_from_invite',
            user_id=user.id,
            token=token,
            _external=True)
        get_queue().enqueue(
            send_email,
            recipient=user.email,
            subject='You Are Invited To Join',
            template='account/email/invite',
            user=user,
            invite_link=invite_link,
        )
        flash('User {} successfully invited'.format(user.full_name()),
              'form-success')
    return render_template('admin/new_user.html', form=form)


@admin.route('/approved-users')
@login_required
@admin_required
def approved_users():
    """View all approved users."""
    users = User.query.filter_by(approved=True)
    roles = Role.query.all()
    return render_template(
        'admin/approved_users.html', users=users, roles=roles)


@admin.route('/view-tags', methods=['GET'])
@login_required
@admin_required
def view_tags():
    """View and manage all tags."""
    Tags = Tag.query.all()
    tag_types = TagType.query.all()
    form = AddTagForm()
    form.tag_type.choices = [(t.id, t.tag_type_name) for t in TagType.query.all()]
    return render_template(
        'admin/view_tags.html',tags=Tags, form=form, tag_types=tag_types)


@admin.route('/delete-tag/<int:tag_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def delete_tag(tag_id):
    """ delete tag """
    tag = Tag.query.filter_by(id=tag_id).first()
    if tag is None:
        return render_template('errors/404.html')
    form = DeleteTagForm()
    form.tag_name.data = tag.tag_name
    if form.validate_on_submit():
        db.session.delete(tag)
        db.session.commit()
        return redirect(url_for('admin.view_tags'))
    return render_template(
             'admin/edit_tag.html',form=form, tag_id=tag_id)


@admin.route('/edit-tag/<int:tag_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_tag(tag_id):
    """ edit tag """
    tag = Tag.query.filter_by(id=tag_id).first()
    if tag is None:
        return render_template('/errors/404.html')
    else:
        form = EditTagForm(tag_name=tag.tag_name)
        if form.validate_on_submit():
            tag.tag_name = form.tag_name.data
            tag.tag_class_name = re.sub('[^0-9a-zA-Z]+', '_', form.tag_name.data)
            db.session.add(tag)
            db.session.commit()
            flash('Tag {} edited successfully.'.format(
                tag.tag_name), 'form-success')
            return redirect(url_for('admin.view_tags'))
    return render_template('admin/edit_tag.html', form=form, tag_id=tag_id)


@admin.route('/add-new-tag', methods=['GET', 'POST'])
@login_required
@admin_required
def add_new_tag():
    """Add a new tag."""
    form = AddTagForm()
    form.tag_type.choices = [(t.id, t.tag_type_name) for t in TagType.query.all()]
    if form.validate_on_submit():
        for t in TagType.query.all():
            if form.tag_type.data == t.id:
                tag = Tag.query.filter_by(tag_name=form.tag_name.data,
                            tag_type=t).first()
                if tag is None:
                    tag_class_name = re.sub('[^0-9a-zA-Z]+', '_', form.tag_name.data)
                    tag = Tag(
                        tag_name=form.tag_name.data,
                        tag_class_name=tag_class_name,
                        tag_type=t,
                        tag_type_id=t.id
                    )
                    try:
                        db.session.commit()
                        flash('Tag {} created successfully.'.format(
                        tag.tag_name), 'form-success')
                    except IntegrityError:
                        db.session.rollback()
                else:
                    flash('The tag of this type already exists', 'error')
    return render_template(
        'admin/add_tag.html' , form=form)


@admin.route('/unapproved-users')
@login_required
@admin_required
def unapproved_users():
    """View all unapproved users."""
    users = User.query.filter_by(approved=False)
    roles = Role.query.all()
    return render_template(
        'admin/unapproved_users.html', users=users, roles=roles)


@admin.route('/unapproved-users/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def approve_user(user_id):
    """Approve a user's profile."""
    user = User.query.filter_by(id=user_id).first()
    user.approved = True
    db.session.add(user)
    db.session.commit()
    users = User.query.filter_by(approved=False)
    roles = Role.query.all()
    if user is None:
        abort(404)
    flash('Successfully approved user %s.' % user.full_name(), 'success')
    return render_template(
        'admin/unapproved_users.html', users=users, roles=roles)

@admin.route('/approved-users/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def unapprove_user(user_id):
    """Unapprove a user's profile."""
    user = User.query.filter_by(id=user_id).first()
    user.approved = False
    db.session.add(user)
    db.session.commit()
    users = User.query.filter_by(approved=True)
    roles = Role.query.all()
    if user is None:
        abort(404)
    flash('Successfully unapproved user %s.' % user.full_name(), 'success')
    return render_template(
        'admin/approved_users.html', users=users, roles=roles)

@admin.route('/user/<int:user_id>')
@admin.route('/user/<int:user_id>/info')
@login_required
@admin_required
def user_info(user_id):
    """View a user's profile."""
    user = User.query.filter_by(id=user_id).first()
    if user is None:
        abort(404)
    return render_template('admin/manage_user.html', user=user)


@admin.route('/user/<int:user_id>/change-email', methods=['GET', 'POST'])
@login_required
@admin_required
def change_user_email(user_id):
    """Change a user's email."""
    user = User.query.filter_by(id=user_id).first()
    if user is None:
        abort(404)
    form = ChangeUserEmailForm()
    if form.validate_on_submit():
        user.email = form.email.data
        db.session.add(user)
        db.session.commit()
        flash('Email for user {} successfully changed to {}.'.format(
            user.full_name(), user.email), 'form-success')
    return render_template('admin/manage_user.html', user=user, form=form)


@admin.route(
    '/user/<int:user_id>/change-account-type', methods=['GET', 'POST'])
@login_required
@admin_required
def change_account_type(user_id):
    """Change a user's account type."""
    if current_user.id == user_id:
        flash('You cannot change the type of your own account. Please ask '
              'another administrator to do this.', 'error')
        return redirect(url_for('admin.user_info', user_id=user_id))

    user = User.query.get(user_id)
    if user is None:
        abort(404)
    form = ChangeAccountTypeForm()
    if form.validate_on_submit():
        user.role = form.role.data
        db.session.add(user)
        db.session.commit()
        flash('Role for user {} successfully changed to {}.'.format(
            user.full_name(), user.role.name), 'form-success')
    return render_template('admin/manage_user.html', user=user, form=form)


@admin.route('/user/<int:user_id>/delete')
@login_required
@admin_required
def delete_user_request(user_id):
    """Request deletion of a user's account."""
    user = User.query.filter_by(id=user_id).first()
    if user is None:
        abort(404)
    return render_template('admin/manage_user.html', user=user)


@admin.route('/user/<int:user_id>/_delete')
@login_required
@admin_required
def delete_user(user_id):
    """Delete a user's account."""
    if current_user.id == user_id:
        flash('You cannot delete your own account. Please ask another '
              'administrator to do this.', 'error')
    else:
        user = User.query.filter_by(id=user_id).first()
        org = Organization.query.filter_by(user_id=user_id).first()
        db.session.delete(user)
        if org is not None:
            db.session.delete(org)
        db.session.commit()
        flash('Successfully deleted user %s.' % user.full_name(), 'success')
    return redirect(url_for('admin.approved_users'))


@admin.route('/_update_editor_contents', methods=['POST'])
@login_required
@admin_required
def update_editor_contents():
    """Update the contents of an editor."""

    edit_data = request.form.get('edit_data')
    editor_name = request.form.get('editor_name')

    editor_contents = EditableHTML.query.filter_by(
        editor_name=editor_name).first()
    if editor_contents is None:
        editor_contents = EditableHTML(editor_name=editor_name)
    editor_contents.value = edit_data

    db.session.add(editor_contents)
    db.session.commit()

    return 'OK', 200
