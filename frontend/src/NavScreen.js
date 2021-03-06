import React from 'react';
import {Menu} from "semantic-ui-react";
import styled from 'styled-components';
import {ThemeVariables} from "./ThemeVariables";
import {NavLink} from "react-router-dom";

const NavScreen = () => {

    return (
        <NavWrapper>
            <Menu inverted pointing secondary>
                <Menu.Item
                    name='home'
                    as={NavLink} to="/"

                />
                <Menu.Item
                    name='coins'
                    as={NavLink} to="/coins"
                />
            </Menu>
        </NavWrapper>
    );
};


const NavWrapper = styled.div`
  background-color: ${ThemeVariables.BackgroundColor};
`;


export default NavScreen;